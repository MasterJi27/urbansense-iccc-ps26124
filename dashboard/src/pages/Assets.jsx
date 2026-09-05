import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Empty from "../components/Empty.jsx";

export default function Assets() {
  const [rows, setRows] = useState([]);
  const [q,setQ]=useState(""); const [typeF,setTypeF]=useState("ALL"); const [cond,setCond]=useState("ALL");
  const [err, setErr] = useState("");
  useEffect(()=>{ api("/assets").then(setRows).catch((e)=>setErr(e.message)); },[]);
  const types=[...new Set(rows.map(r=>r.asset_type))].sort();
  const filtered=useMemo(()=>{
    let r=[...rows];
    if(q) r=r.filter(a=>`${a.code} ${a.name} ${a.asset_type}`.toLowerCase().includes(q.toLowerCase()));
    if(typeF!=="ALL") r=r.filter(a=>a.asset_type===typeF);
    if(cond!=="ALL") r=r.filter(a=>a.condition===cond);
    return r;
  },[rows,q,typeF,cond]);
  if (err) return <p className="err">{err}</p>;
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">INFRASTRUCTURE • PASSPORTS</div><h2 className="page-title">Infrastructure passports</h2><p className="page-sub muted" role="status"><span className="table-num">{filtered.length} of {rows.length}</span> assets • QR-bound • GIS asset-watch for missing/divider/zebra/sign</p></div>
        <div className="filters" role="group" aria-label="Condition filter">{["ALL","GOOD","FAIR","POOR","CRITICAL"].map(c=>(<button key={c} className={`chip ${cond===c?"active":""}`} aria-pressed={cond===c} onClick={()=>setCond(c)}>{c==="ALL"?"All":c}</button>))}<input placeholder="Search code / name" aria-label="Search assets" value={q} onChange={e=>setQ(e.target.value)} /><select aria-label="Filter by asset type" value={typeF} onChange={e=>setTypeF(e.target.value)}><option value="ALL">All types</option>{types.map(t=><option key={t} value={t}>{t}</option>)}</select><select aria-label="Filter by condition" value={cond} onChange={e=>setCond(e.target.value)}><option value="ALL">All conditions</option><option>GOOD</option><option>FAIR</option><option>POOR</option><option>CRITICAL</option></select></div>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(300px,1fr))",gap:12}}>
        {filtered.map((a)=>(
          <Link key={a.id} to={`/assets/${a.id}`} className="card" style={{display:"block"}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span style={{display:"flex",alignItems:"center",gap:8}}><span className={`status-dot ${a.condition==="GOOD"?"on":a.condition==="FAIR"?"warn":"bad"}`} aria-hidden="true" /><b className="mono" style={{fontSize:13}}>{a.code}</b></span><span className={`tag ${a.condition==="GOOD"?"real": a.condition==="CRITICAL"?"sim":"rule"}`} style={{fontSize:11}}>{a.condition}</span>
            </div>
            <h4 style={{fontSize:13,letterSpacing:"0",textTransform:"none",color:"var(--text)",margin:"6px 0 0"}}>{a.name}</h4>
            <div className="muted" style={{fontSize:12}}>{a.asset_type?.replaceAll("_"," ")}</div>
            <div className="mono muted" style={{fontSize:11,marginTop:8,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{a.qr_payload}</div>
            <div className="muted table-num" style={{fontSize:11,marginTop:4}}>{Number(a.latitude).toFixed(4)}, {Number(a.longitude).toFixed(4)}</div>
          </Link>
        ))}
      </div>
      {filtered.length===0 && <Empty icon="▦" title="No assets match" description="Try clearing filters — or POST /assets/SIGN-183/passes ×3 to trigger missing-infra demo." actionLabel={(q||typeF!=="ALL"||cond!=="ALL")?"Clear filters":undefined} onAction={(q||typeF!=="ALL"||cond!=="ALL")?()=>{setQ("");setTypeF("ALL");setCond("ALL");}:undefined} style={{marginTop:12}} />}
    </div>
  );
}
