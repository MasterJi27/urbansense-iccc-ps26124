import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Empty from "../components/Empty.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import { useUi } from "../i18n.jsx";
import { delhiZone, priorityBand, repairPriority } from "../honesty.js";

function timeAgo(ts){
  if(!ts) return "unknown age";
  const s=Math.floor((Date.now()-new Date(ts).getTime())/1000);
  if(Number.isNaN(s)||s<0) return "just now";
  if(s<60) return `${s}s ago`;
  const m=Math.floor(s/60);
  if(m<60) return `${m}m ago`;
  const h=Math.floor(m/60);
  if(h<24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
}

const statusColor={ PENDING:"tag info", ASSIGNED:"tag real", IN_PROGRESS:"badge MEDIUM", COMPLETED:"badge LOW", RE_VERIFICATION:"tag sim", RESOLVED:"tag real", FAILED:"badge CRITICAL" };

export default function WorkOrders() {
  const { t } = useUi();
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  const [filter,setFilter]=useState("ALL");
  const [zoneF,setZoneF]=useState("ALL");
  function load(){ api("/work-orders").then(setRows).catch((e)=>setErr(e.message)); }
  useEffect(load, []);
  if (err) return <p className="err">{err}</p>;
  const zones = [...new Set(rows.map((w) => delhiZone(w.latitude, w.longitude).zone))].filter((z) => z && z !== "—");
  const view = (filter==="ALL"?rows:rows.filter(r=>r.status===filter)).filter((w)=>{
    if (zoneF === "ALL") return true;
    return delhiZone(w.latitude, w.longitude).zone === zoneF;
  }).slice().sort((a,b)=>{
    const pa = repairPriority({ severity: a.event_severity, observationCount: a.observation_count, sourceCount: a.source_count });
    const pb = repairPriority({ severity: b.event_severity, observationCount: b.observation_count, sourceCount: b.source_count });
    return pb - pa;
  });
  const statuses=[...new Set(rows.map(r=>r.status))];
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">ICCC • {t("workOrders").toUpperCase()}</div><h2 className="page-title">{t("pageWo")}</h2><p className="page-sub muted">{t("pageWoSub")} • <span role="status"><span className="table-num">{view.length}</span> {t("of")} <span className="table-num">{rows.length}</span></span></p></div>
        <div className="filters">
          <select aria-label="Filter work orders by status" value={filter} onChange={e=>setFilter(e.target.value)}><option value="ALL">All statuses</option>{statuses.map(s=><option key={s} value={s}>{s}</option>)}</select>
          <select aria-label="Filter by ICCC zone" value={zoneF} onChange={e=>setZoneF(e.target.value)}><option value="ALL">{t("zone")} — all</option>{zones.map((z)=><option key={z} value={z}>{z}</option>)}</select>
        </div>
      </div>

      <div className="grid-4" style={{marginBottom:14}}>
        {["PENDING","ASSIGNED","IN_PROGRESS","RESOLVED","FAILED"].map(k=>{
          const n=rows.filter(r=>r.status===k).length;
          const mod=k==="PENDING"&&n>5?"warn":k==="FAILED"&&n>0?"crit":"";
          return <div key={k} className={`card ${mod}`} style={{padding:"12px 14px"}}><h4>{k.replace("_"," ")}</h4><div className="n table-num" style={{fontSize:22}}>{n}</div></div>;
        })}
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(320px,1fr))",gap:12}}>
        {view.map((w)=>{
          const accent={PENDING:"var(--info)",ASSIGNED:"var(--accent)",FAILED:"var(--danger)"}[w.status]||"transparent";
          const loc = delhiZone(w.latitude, w.longitude);
          const pri = repairPriority({
            severity: w.event_severity,
            observationCount: w.observation_count,
            sourceCount: w.source_count,
          });
          const band = priorityBand(pri);
          return (
          <div key={w.id} className="card" style={{display:"flex",flexDirection:"column",gap:8,borderTop:`3px solid ${accent}`}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <b className="mono" style={{fontSize:13}}>{w.public_code}</b><span className={statusColor[w.status]||"tag"} style={{fontSize:11,fontWeight:700}}>{w.status}</span>
            </div>
            <h4 style={{margin:0,fontSize:13,letterSpacing:"0",textTransform:"none",color:"var(--text)",fontWeight:700,lineHeight:1.3}}>{w.title}</h4>
            <div className="wo-meta">
              <span className="tag info">{t("zone")} {loc.zone}</span>
              <span className="tag rule">{loc.ward}</span>
              <span className={`badge ${band}`}>{t("priority")} {pri}</span>
              <HonestyChip event={{ event_type: w.event_type, simulated: w.simulated, extra: { ai_status: w.ai_status } }} compact />
            </div>
            <div className="muted" style={{fontSize:12}}>{w.description || "ICCC → ward engineer. Re-sense after repair."}</div>
            <div className="mono muted" style={{fontSize:11,wordBreak:"break-all"}}>{w.qr_payload}</div>
            <div className="muted" style={{fontSize:11}}>Event {w.event_code || w.event_id?.slice(0,8)} {w.event_type?`• ${w.event_type}`:""} • {timeAgo(w.created_at)}{w.event_id && <> • <Link to={`/events/${w.event_id}`}>View event</Link></>}</div>
          </div>
          );
        })}
      </div>
      {view.length===0 && <Empty icon="✓" title="No work orders" description="Create from Event Detail → Create work order, or run JURY RUN (8 min)." actionLabel={filter!=="ALL"?"Clear filter":undefined} onAction={filter!=="ALL"?()=>setFilter("ALL"):undefined} style={{marginTop:14}} />}
    </div>
  );
}
