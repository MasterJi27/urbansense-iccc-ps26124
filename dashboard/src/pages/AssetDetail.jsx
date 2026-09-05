import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { CircleMarker } from "react-leaflet";
import CorridorMap from "../components/CorridorMap.jsx";
import { api } from "../api";
import { Skeleton } from "../components/Skeleton.jsx";

export default function AssetDetail(){
  const { id } = useParams();
  const [a,setA]=useState(null);
  const [err,setErr]=useState("");
  const [tab,setTab]=useState("timeline");
  const [chk,setChk]=useState({joint_gap:"", bearing:"GOOD", crack:"", waterlogging:"DRY", overall:"FAIR", notes:""});
  const [chkMsg,setChkMsg]=useState("");
  const [chkSaving,setChkSaving]=useState(false);
  useEffect(()=>{ api(`/assets/${id}`).then(setA).catch(e=>setErr(e.message)); },[id]);
  async function submitInspect(e){
    e.preventDefault();
    setChkSaving(true); setChkMsg("");
    try{
      await api(`/assets/${id}/inspect`, {method:"POST", body: JSON.stringify({joint_gap: chk.joint_gap||null, bearing: chk.bearing||null, crack: chk.crack||null, waterlogging: chk.waterlogging||null, overall: chk.overall||null, notes: chk.notes||""})});
      setChkMsg("✓ Saved");
      const fresh = await api(`/assets/${id}`); setA(fresh);
    }catch(ex){ setChkMsg(ex.message); } finally{ setChkSaving(false); }
  }
  if(err) return <p className="err">{err}</p>;
  if(!a) return (
    <div>
      <div className="card" style={{ marginBottom: 12 }}>
        <Skeleton width="22%" height={10} style={{ marginBottom: 10 }} />
        <Skeleton width="38%" height={24} style={{ marginBottom: 8 }} />
        <Skeleton width="72%" height={12} />
      </div>
      <div className="asset-detail-grid">
        <div style={{ display: "grid", gap: 12 }}>
          <div className="card"><Skeleton height={220} /></div>
          <div className="card"><Skeleton height={180} /></div>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          <div className="card"><Skeleton height={280} /></div>
          <div className="card"><Skeleton height={160} /></div>
        </div>
      </div>
    </div>
  );

  const isBridge = a.asset_type==="BRIDGE"||a.asset_type==="FLYOVER";
  const health = Number(a.health_score ?? 70);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="crumbs"><Link to="/assets">Assets</Link> • {a.asset_type}</div>
          <h2 className="page-title" style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>{a.code} <span className="mono" style={{fontSize:13,fontWeight:700}}>{a.name}</span> <span style={{display:"inline-flex",alignItems:"center",gap:6}}><span className={`status-dot ${a.condition==="GOOD"?"on":a.condition==="FAIR"?"warn":"bad"}`} aria-hidden="true" /><span className={`tag ${a.condition==="GOOD"?"real": a.condition==="CRITICAL"?"sim":"rule"}`} style={{fontSize:11}}>{a.condition}</span></span></h2>
          <p className="page-sub muted" role="status" style={{fontSize:12}}><span className="table-num">{a.latitude.toFixed(5)}, {a.longitude.toFixed(5)}</span> • health <span className="table-num">{health.toFixed(0)}/100</span> {isBridge && a.span_m?`• ${a.span_m}m span`:""} • <span className="mono">{a.qr_payload}</span></p>
        </div>
        <div className="filters" role="tablist" aria-label="Asset detail tabs">
          <button role="tab" aria-selected={tab==="timeline"} aria-pressed={tab==="timeline"} className={`chip ${tab==="timeline"?"active":""}`} onClick={()=>setTab("timeline")}>Timeline</button>
          <button role="tab" aria-selected={tab==="events"} aria-pressed={tab==="events"} className={`chip ${tab==="events"?"active":""}`} onClick={()=>setTab("events")}>Events</button>
          <button role="tab" aria-selected={tab==="shm"} aria-pressed={tab==="shm"} className={`chip ${tab==="shm"?"active":""}`} onClick={()=>setTab("shm")}>SHM</button>
          <Link className="btn ghost" to={`/bridge`}>Bridge SHM →</Link>
        </div>
      </div>

      <div className="asset-detail-grid">
        <div style={{display:"grid",gap:12}}>
          <div className="card" style={{padding:0,overflow:"hidden"}}>
            <div style={{padding:"12px 14px",display:"flex",justifyContent:"space-between",alignItems:"center",borderBottom:"1px solid var(--line)"}}>
              <h4 style={{margin:0}}>Digital passport</h4>
              <span className={`tag ${health<50?"sim": health<70?"rule":"real"}`} style={{fontSize:11}}>{health<50?"watch": health<70?"fair":"healthy"} • {health.toFixed(0)}</span>
            </div>
            <div className="grid-2" style={{padding:14}}>
              <div><div className="muted" style={{fontSize:11,letterSpacing:".07em",textTransform:"uppercase",fontWeight:700}}>Health</div><div style={{display:"flex",gap:8,alignItems:"center",marginTop:6}}><div style={{flex:1,height:8,background:"var(--line)",borderRadius:999,overflow:"hidden"}}><div style={{width:`${health}%`,height:"100%",background: health<50?"var(--danger)": health<70?"var(--warn)":"var(--accent)"}} /></div><b className="table-num">{health.toFixed(0)}</b></div></div>
              <div><div className="muted" style={{fontSize:11,letterSpacing:".07em",textTransform:"uppercase",fontWeight:700}}>Condition</div><div style={{marginTop:6,display:"flex",alignItems:"center",gap:6}}><span className={`status-dot ${a.condition==="GOOD"?"on":a.condition==="FAIR"?"warn":"bad"}`} aria-hidden="true" /><span className={`badge ${health<50?"CRITICAL": health<70?"MEDIUM":"LOW"}`}>{a.condition}</span></div></div>
              <div><div className="muted" style={{fontSize:11,letterSpacing:".07em",textTransform:"uppercase",fontWeight:700}}>Location</div><div className="mono table-num" style={{fontSize:12,marginTop:6}}>{a.latitude.toFixed(5)}, {a.longitude.toFixed(5)}</div><div className="muted" style={{fontSize:11}}>{isBridge?`Span ${a.span_m ?? "—"}m • baseline ${a.shm_baseline_rms?.toFixed(3) ?? "—"}g`:""}</div></div>
              <div><div className="muted" style={{fontSize:11,letterSpacing:".07em",textTransform:"uppercase",fontWeight:700}}>QR</div><div className="mono table-num" style={{fontSize:11,marginTop:6,wordBreak:"break-all",background:"var(--surface-2)",padding:"6px 8px",borderRadius:8,border:"1px solid var(--line)"}}>{a.qr_payload}</div><button className="btn ghost btn-sm" title="Copy QR payload" style={{marginTop:6,fontSize:11}} onClick={()=>navigator.clipboard.writeText(a.qr_payload)}>Copy</button></div>
              { isBridge && (
                <>
                  <div><div className="muted" style={{fontSize:11,fontWeight:700}}>SHM baseline</div><div className="mono table-num" style={{fontSize:12}}>{a.health_score? `${Number(a.health_score).toFixed(0)}/100`:"—"} • RMS {a.shm_baseline_rms?.toFixed(3) ?? "—"}g • f {a.shm_baseline_freq?.toFixed(1) ?? "—"}Hz</div></div>
                  <div><div className="muted" style={{fontSize:11,fontWeight:700}}>Predicted</div><div style={{fontSize:12, color: a.predicted_days_to_maintenance?"var(--danger)":"var(--muted)"}}>{a.predicted_days_to_maintenance? `${a.predicted_days_to_maintenance} days to maintenance`:"stable"}</div></div>
                </>
              )}
            </div>
            <div style={{padding:"0 14px 14px",display:"flex",gap:8,flexWrap:"wrap"}}>
              <span className="tag info" style={{fontSize:11}}>ID {a.id.slice(0,8)}</span>
              <span className="tag info" style={{fontSize:11}}>{a.asset_type}</span>
              {isBridge && <Link className="tag real" style={{fontSize:11}} to="/bridge">Open SHM →</Link>}
            </div>
          </div>

          {tab==="timeline" && (
            <div className="card">
              <h4>Timeline — inspections, events, work orders</h4>
              <div className="timeline">
                {(a.timeline||[]).length===0 && <div className="empty"><b>No history yet</b><div className="muted">Events near this asset will appear here (0.002° window).</div></div>}
                {(a.timeline||[]).slice(0,18).map((t,i)=>(
                  <div key={i} className={`tl-item ${i===0?"active":""}`}>
                    <div className="title" style={{fontWeight:700}}>{t.label} <span className="muted" style={{fontWeight:400}}>• {t.detail}</span></div>
                    <div className="meta mono-sm table-num">{t.at? new Date(t.at).toLocaleString(): "—"}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab==="events" && (
            <div className="card">
              <h4>Linked events (nearby 0.002°)</h4>
              {(a.events||[]).length===0 && <div className="empty"><b>No linked events</b><div className="muted">Emit a SHM batch or pothole near {a.code} to link.</div></div>}
              <div style={{display:"grid",gap:8}}>
                {(a.events||[]).map(e=>(
                  <Link key={e.id} to={`/events/${e.id}`} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"10px 12px",border:"1px solid var(--line)",borderRadius:10}}>
                    <span><b className="mono" style={{fontSize:12}}>{e.public_code}</b><span className="muted" style={{marginLeft:6,fontSize:11}}>{e.event_type}</span></span>
                    <span className={`badge ${e.status}`} style={{fontSize:10}}>{e.status}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {tab==="shm" && (
            <div className="card">
              <h4>SHM — vibration ledger</h4>
              {!isBridge && <p className="muted" style={{fontSize:12}}>SHM only for BRIDGE/FLYOVER. This asset is {a.asset_type}.</p>}
              {isBridge && <div>
                <p className="muted" style={{fontSize:11}}>Baseline RMS {a.shm_baseline_rms?.toFixed(3)}g • last {a.shm_last_rms?.toFixed(3)}g • anomalies {a.shm_anomaly_count ?? 0} • f_dom {a.shm_last_freq?.toFixed(1) ?? "—"}Hz • predicted {a.predicted_days_to_maintenance ?? "—"}d</p>
                <div style={{display:"flex",gap:8,marginTop:8}}>
                  <Link className="btn" to="/bridge">Open Bridge SHM</Link>
                  <Link className="btn ghost" to={`/bridge/${a.id}`}>History</Link>
                </div>
              </div>}
            </div>
          )}
        </div>

        <div style={{display:"grid",gap:12}}>
          <div className="card" style={{padding:0,overflow:"hidden"}}>
            <div style={{padding:"10px 14px",borderBottom:"1px solid var(--line)",display:"flex",justifyContent:"space-between"}}><h4 style={{margin:0}}>Location</h4><span className="muted" style={{fontSize:11}}>{a.qr_payload.slice(-12)}</span></div>
            <CorridorMap center={[a.latitude,a.longitude]} zoom={16} height={280} hideCaption>
              <CircleMarker center={[a.latitude,a.longitude]} radius={13} pathOptions={{color: health<50?"#e5484d": health<70?"#b7790f":"#0bb98a", fillOpacity:.18, weight:2}} />
            </CorridorMap>
            <div style={{padding:10}}><div className="mono table-num" style={{fontSize:12}}>{a.latitude.toFixed(5)}, {a.longitude.toFixed(5)}</div><div className="muted" style={{fontSize:11}}>Snap geofence 70m • crowd baseline per-bridge</div></div>
          </div>

          <div className="card">
            <h4>Work orders</h4>
            {(a.work_orders||[]).length===0 && <div className="empty" style={{padding:12}}><b>None</b><div className="muted">CRITICAL SHM auto-creates WO-BR-*</div></div>}
            {(a.work_orders||[]).map(w=>{
              const exif = (()=>{ try{
                const url=w.repair_evidence_url||"";
                if(!url) return null;
                const mLat=url.match(/lat=([0-9.\-]+)/), mLon=url.match(/lon=([0-9.\-]+)/), mT=url.match(/[?&]t=([^&]+)/), mAcc=url.match(/acc=([^&#&]+)/), mBridge=url.match(/bridge=([^&#]+)/);
                const lat=mLat?parseFloat(mLat[1]):null, lon=mLon?parseFloat(mLon[1]):null;
                const t=mT?decodeURIComponent(mT[1]):null;
                const acc=mAcc?decodeURIComponent(mAcc[1]):null;
                const bridge=mBridge?decodeURIComponent(mBridge[1]):null;
                if(lat||lon||t) return {lat,lon,t,acc,bridge,url};
                return null;
              }catch{return null;}})();
              return (
              <div key={w.id} style={{padding:"8px 0",borderBottom:"1px solid var(--line)"}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><b className="mono" style={{fontSize:12}}>{w.public_code}</b><span className="tag info" style={{fontSize:11}}>{w.status}</span></div>
                {w.title && <div className="muted" style={{fontSize:11,marginTop:2}}>{w.title}</div>}
                {w.repair_evidence_url ? (
                  <div style={{marginTop:6, padding:"8px 10px", background:"var(--surface-2)", border:"1px solid var(--line)", borderRadius:8}}>
                    <div className="muted" style={{fontSize:10,letterSpacing:".07em",textTransform:"uppercase",fontWeight:700}}>Photo evidence • EXIF GPS</div>
                    <a href={w.repair_evidence_url} className="mono" style={{fontSize:11,wordBreak:"break-all",display:"block",marginTop:4}}>{w.repair_evidence_url}</a>
                    {exif ? <div className="mono" style={{fontSize:11,marginTop:4}}>📍 {exif.lat?.toFixed(5) ?? "—"}, {exif.lon?.toFixed(5) ?? "—"} {exif.acc?`±${exif.acc}m`:""} • {exif.t? new Date(exif.t).toLocaleString(): (w.updated_at? new Date(w.updated_at).toLocaleString():"—")} {exif.bridge?`• ${exif.bridge}`:""}</div> : <div className="mono" style={{fontSize:11,marginTop:4}}>No GPS in URL — legacy evidence</div>}
                    {w.repair_notes && <div className="muted" style={{fontSize:11,marginTop:4,wordBreak:"break-word"}}>notes: {w.repair_notes.slice(0,180)}</div>}
                    <div className="muted" style={{fontSize:10,marginTop:4}}>Embedded by mobile _attachJointPhoto ?lat=&lon=&t=&acc= → queued extra lat/lon → POST /work-orders/{"{id}"}/repair</div>
                  </div>
                ) : <div className="muted" style={{fontSize:11,marginTop:4}}>No photo evidence yet — attach joint photo in mobile SHM.</div>}
              </div>);
            })}
          </div>

          <div className="card">
            <h4>Bridge Inspection Checklist</h4>
            <p className="muted" style={{fontSize:11,marginTop:4}}>Joint gap, bearing, crack, waterlogging, overall → POST /assets/{`{id}`}/inspect (stores JSON in Inspection.checklist)</p>
            <form onSubmit={submitInspect} style={{display:"grid",gap:8,marginTop:10}}>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
                <label style={{fontSize:11,fontWeight:700}}>Joint gap <input value={chk.joint_gap} onChange={e=>setChk({...chk,joint_gap:e.target.value})} placeholder="12.5 mm or OK/WATCH" style={{width:"100%",marginTop:4,padding:"6px 8px",border:"1px solid var(--line)",borderRadius:8}} /></label>
                <label style={{fontSize:11,fontWeight:700}}>Bearing <select value={chk.bearing} onChange={e=>setChk({...chk,bearing:e.target.value})} style={{width:"100%",marginTop:4,padding:"6px 8px",border:"1px solid var(--line)",borderRadius:8}}><option>GOOD</option><option>FAIR</option><option>WORN</option><option>CRITICAL</option></select></label>
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
                <label style={{fontSize:11,fontWeight:700}}>Crack <input value={chk.crack} onChange={e=>setChk({...chk,crack:e.target.value})} placeholder="45 mm or LOW/MEDIUM/HIGH" style={{width:"100%",marginTop:4,padding:"6px 8px",border:"1px solid var(--line)",borderRadius:8}} /></label>
                <label style={{fontSize:11,fontWeight:700}}>Waterlogging <select value={chk.waterlogging} onChange={e=>setChk({...chk,waterlogging:e.target.value})} style={{width:"100%",marginTop:4,padding:"6px 8px",border:"1px solid var(--line)",borderRadius:8}}><option>DRY</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>WATERLOGGED</option></select></label>
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
                <label style={{fontSize:11,fontWeight:700}}>Overall* <select value={chk.overall} onChange={e=>setChk({...chk,overall:e.target.value})} style={{width:"100%",marginTop:4,padding:"6px 8px",border:"1px solid var(--line)",borderRadius:8}}><option>GOOD</option><option>FAIR</option><option>POOR</option><option>CRITICAL</option><option>UNKNOWN</option></select></label>
                <label style={{fontSize:11,fontWeight:700}}>Notes <input value={chk.notes} onChange={e=>setChk({...chk,notes:e.target.value})} placeholder="optional" style={{width:"100%",marginTop:4,padding:"6px 8px",border:"1px solid var(--line)",borderRadius:8}} /></label>
              </div>
              <div style={{display:"flex",gap:8,alignItems:"center"}}>
                <button className="btn" type="submit" disabled={chkSaving} style={{flex:1}}>{chkSaving?"Saving…":"Submit checklist"}</button>
                {chkMsg && <span className="muted" style={{fontSize:11}}>{chkMsg}</span>}
              </div>
            </form>
          </div>

          <div className="card">
            <h4>Inspections</h4>
            {(a.inspections||[]).length===0 && <div className="muted" style={{fontSize:12}}>No inspections yet.</div>}
            {(a.inspections||[]).map(ins=>(
              <div key={ins.id} style={{padding:"8px 0",borderBottom:"1px solid var(--line)"}}>
                <div style={{fontWeight:700,fontSize:12}}>{ins.condition} <span className="muted" style={{fontWeight:400}}>• {ins.notes.slice(0,80)}</span></div>
                {ins.checklist && <div style={{display:"flex",gap:6,flexWrap:"wrap",marginTop:4}}>{["joint_gap","bearing","crack","waterlogging","overall"].map(k=> ins.checklist[k]!=null ? <span key={k} className="tag info" style={{fontSize:10}}>{k}:{String(ins.checklist[k])}</span> : null)}</div>}
                <div className="muted" style={{fontSize:11}}>{new Date(ins.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
