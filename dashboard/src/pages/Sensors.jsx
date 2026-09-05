import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Empty from "../components/Empty.jsx";

function timeAgo(ts){
  if(!ts) return "never";
  const s=Math.floor((Date.now()-new Date(ts).getTime())/1000);
  if(Number.isNaN(s)||s<0) return "just now";
  if(s<60) return `${s}s ago`;
  const m=Math.floor(s/60);
  if(m<60) return `${m}m ago`;
  const h=Math.floor(m/60);
  if(h<24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
}

export default function Sensors() {
  const [rows, setRows] = useState([]);
  const [q,setQ]=useState("");
  useEffect(()=>{ const load=()=>api("/sensor-nodes").then(setRows); load(); const t=setInterval(load,8000); return()=>clearInterval(t); },[]);
  const filtered = rows.filter(s=> !q || `${s.code} ${s.bus_code} ${s.device_label}`.toLowerCase().includes(q.toLowerCase()));
  const online = rows.filter(s=>s.camera_status==="ONLINE").length;
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">SYSTEM • SENSORS</div><h2 className="page-title">Sensor fleet</h2><p className="page-sub muted">Heartbeat 12s • edge modes HIGH/MEDIUM/LOW • <span role="status"><span className="table-num">{filtered.length}</span> of <span className="table-num">{rows.length}</span> sensors • <span className="table-num">{online}/{rows.length}</span> cameras online</span></p></div>
        <div className="filters"><input placeholder="Search sensor / bus" aria-label="Search sensors" value={q} onChange={e=>setQ(e.target.value)} /><span className={`tag ${online>0?"real":"rule"}`}>{online} online</span><Link className="btn ghost" to="/cctv">CCTV BRIDGE</Link></div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:12}}>
        {filtered.map((s)=>(
          <div className="card" key={s.id} style={{display:"flex",flexDirection:"column",gap:6}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span style={{display:"inline-flex",alignItems:"center",gap:8}}><span className={`status-dot ${s.camera_status==="ONLINE"?"on":"off"}`} aria-hidden="true" /><h4 style={{margin:0,fontSize:13,letterSpacing:"0",textTransform:"none",color:"var(--text)"}}>{s.bus_code || s.code}</h4></span><span className={`tag ${s.camera_status==="ONLINE"?"real":"rule"}`} style={{fontSize:11}}>{s.camera_status}</span>
            </div>
            <div className="muted mono" style={{fontSize:11}}>{s.code} • {s.device_label} • {s.processing_mode?.replaceAll("_"," ")}</div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:6,fontSize:12,marginTop:4}}>
              <div>GPS <b>{s.gps_status}</b></div><div>IMU <b>{s.imu_status}</b></div>
              <div>Network <b>{s.network_type || "—"}</b></div><div>Battery <b className="table-num" style={s.battery_pct!=null&&s.battery_pct<20?{color:"var(--warn)"}:undefined}>{s.battery_pct!=null?`${s.battery_pct}%`:"n/a"}</b>{s.battery_pct!=null&&s.battery_pct<20&&<span className="tag sim" style={{fontSize:10,marginLeft:6}}>LOW</span>}</div>
              <div>AI <b>{s.ai_mode}</b></div><div>Sync <b>{s.sync_state || "IDLE"}</b></div>
            </div>
            <div className="muted" style={{fontSize:11,marginTop:6}}>Heartbeat {timeAgo(s.last_heartbeat_at)}</div>
            {s.latitude && <div className="mono muted table-num" style={{fontSize:11}}>{Number(s.latitude).toFixed(4)}, {Number(s.longitude).toFixed(4)}</div>}
          </div>
        ))}
      </div>
      {filtered.length===0 && <Empty icon="◉" title="No sensors match" description={q ? `No sensors match “${q}”` : "No sensor nodes registered"} actionLabel={q?"Clear search":undefined} onAction={q?()=>setQ(""):undefined} style={{marginTop:12}} />}
    </div>
  );
}
