import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Empty from "../components/Empty.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import { useUi } from "../i18n.jsx";
import { priorityBand, repairPriority } from "../honesty.js";

export default function RoadHealth() {
  const { t } = useUi();
  const [rows, setRows] = useState([]);
  const [q,setQ]=useState("");
  const [sort,setSort]=useState("worst");
  useEffect(()=>{ api("/road-health").then(setRows); },[]);
  const view=useMemo(()=>{
    let r=[...rows];
    if(q) r=r.filter(s=> s.name.toLowerCase().includes(q.toLowerCase()) || s.code.toLowerCase().includes(q.toLowerCase()));
    r.sort((a,b)=> sort==="worst" ? a.health_score - b.health_score : b.health_score - a.health_score);
    return r;
  },[rows,q,sort]);
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">ULB • {t("roadHealth").toUpperCase()}</div><h2 className="page-title">{t("pageRh")}</h2><p className="page-sub muted" role="status"><span className="table-num">{view.length} {t("of")} {rows.length}</span> corridors • {t("pageRhSub")}</p></div>
        <div className="filters"><button className={`chip ${sort==="worst"?"active":""}`} aria-pressed={sort==="worst"} onClick={()=>setSort("worst")}>{t("worst")}</button><button className={`chip ${sort==="best"?"active":""}`} aria-pressed={sort==="best"} onClick={()=>setSort("best")}>{t("best")}</button><input placeholder="Search corridor" aria-label="Search road segments" value={q} onChange={e=>setQ(e.target.value)} /><select aria-label="Sort road health" value={sort} onChange={e=>setSort(e.target.value)}><option value="worst">{t("worst")}</option><option value="best">{t("best")}</option></select></div>
      </div>
      {view.length === 0 ? (
        <div className="table-wrap">
          <Empty
            icon="〰"
            title="No segments found"
            description={q ? `No segments match “${q}”` : "No road segments available"}
            actionLabel={q ? "Clear search" : undefined}
            onAction={q ? () => setQ("") : undefined}
          />
        </div>
      ) : (
        <div className="table-wrap">
          <div style={{overflow:"auto"}}>
            <table>
              <thead><tr><th>Corridor</th><th>Score</th><th>Health</th><th>{t("repairPri")}</th><th>Active defects</th><th>Recurrence</th><th>Traffic</th><th>Pedestrian</th></tr></thead>
              <tbody>
                {view.map((s)=>{
                  const pri = repairPriority({
                    severity: s.health_score < 50 ? "CRITICAL" : s.health_score < 70 ? "HIGH" : "MEDIUM",
                    observationCount: (s.active_defects || 0) + (s.recurrence_count || 0),
                    sourceCount: s.recurrence_count || 1,
                    trafficExposure: s.traffic_exposure,
                    pedestrianExposure: s.pedestrian_exposure,
                  });
                  const band = priorityBand(pri);
                  return (
                  <tr key={s.id}>
                    <td><span className={`status-dot ${s.health_score<50?"bad":s.health_score<70?"warn":"on"}`} aria-hidden="true" /><b>{s.name}</b> <span className={`tag ${s.health_score<50?"sim":s.health_score<70?"rule":"real"}`} style={{fontSize:10}}>{s.health_score<50?"watch":s.health_score<70?"fair":"healthy"}</span><div className="muted mono" style={{fontSize:11}} title={s.code}>{s.code}</div></td>
                    <td><b className="table-num" style={{color: s.health_score<50?"var(--danger)": s.health_score<70?"var(--warn)":"var(--accent-700)"}}>{Number(s.health_score).toFixed(1)}</b></td>
                    <td><div style={{width:120,height:8,background:"var(--line)",borderRadius:999,overflow:"hidden"}}><div style={{width:`${s.health_score}%`,height:"100%",background: s.health_score<50?"var(--danger)": s.health_score<70?"var(--warn)":"var(--accent)"}} /></div></td>
                    <td>
                      <div style={{display:"flex",gap:8,alignItems:"center"}}>
                        <b className="table-num">{pri}</b>
                        <span className={`badge ${band}`} style={{fontSize:10}}>{band}</span>
                        <span className="priority-bar" aria-hidden="true"><i style={{width:`${pri}%`,background: band==="CRITICAL"||band==="HIGH"?"var(--danger)":band==="MEDIUM"?"var(--warn)":"var(--accent)"}} /></span>
                      </div>
                    </td>
                    <td className="table-num">{s.active_defects}</td>
                    <td className="table-num">{s.recurrence_count}</td>
                    <td className="table-num">{s.traffic_exposure}</td>
                    <td className="table-num">{s.pedestrian_exposure}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="card" style={{marginTop:12}}><h4>Formula (transparent) <HonestyChip status="RULE_BASED" compact /></h4><p className="mono" style={{fontSize:11,margin:0,lineHeight:1.6}}>health = 100 − (defects*8 + high*12 + recurrence*5 + traffic*0.02 + pedestrian*0.03)<br/>repair priority = severity×16 + repeats×7 + sources×5 + route importance + VRU exposure • ULB queue sort, not a learned ranker</p></div>
    </div>
  );
}
