import { useEffect, useState } from "react";
import { api } from "../api";
import { Skeleton } from "../components/Skeleton.jsx";
import Empty from "../components/Empty.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import { useUi } from "../i18n.jsx";
import { edgeModeFromProcessing } from "../honesty.js";

function Pill({status}){
  const cls = status==="REAL"?"tag real": status==="RULE_BASED"?"tag rule": status==="DISABLED"?"tag off": status==="EXPERIMENTAL"||status==="SIMULATED"?"tag sim":"tag info";
  return <span className={cls} style={{fontSize:11,fontWeight:700}}>{status}</span>;
}

export default function Settings(){
  const { t } = useUi();
  const [s,setS]=useState(null);
  const [nodes,setNodes]=useState([]);
  const [ai,setAi]=useState(null);
  const [err,setErr]=useState("");
  useEffect(()=>{
    api("/settings").then(setS).catch(e=>setErr(e.message));
    api("/ai/capabilities").then(setAi).catch(()=>setAi({available:false}));
    api("/sensor-nodes").then(setNodes).catch(()=>setNodes([]));
    api("/bridge/geofence").catch(()=>null);
  },[]);
  if(err) return <p className="err">{err}</p>;
  if(!s) return (
    <div>
      <div className="card" style={{ marginBottom: 12 }}>
        <Skeleton width="28%" height={12} style={{ marginBottom: 12 }} />
        <Skeleton height={14} style={{ marginBottom: 8 }} />
        <Skeleton height={14} width="90%" style={{ marginBottom: 8 }} />
        <Skeleton width="70%" height={14} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 10 }}>
        {[0,1,2,3].map((i) => (
          <div key={i} className="card"><Skeleton height={84} /></div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        <div className="card"><Skeleton height={180} /></div>
        <div className="card"><Skeleton height={180} /></div>
      </div>
    </div>
  );
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">SYSTEM • {t("settings").toUpperCase()}</div><h2 className="page-title">{t("pageSet")}</h2><p className="page-sub muted">{t("pageSetSub")} • <span role="status"><span className="table-num">{ai ? Object.keys(ai).length : 0}</span> engines</span></p></div><div className="filters"><span className="tag info"><span className="table-num">{ai ? Object.keys(ai).length : 0}</span> engines</span></div></div>

      <div className="card" style={{ marginBottom: 12 }}>
        <h4>Capture — phones only</h4>
        <div className="stat-row"><span className="muted">ICCC laptop</span><b>This register. Control-room Chrome/Edge.</b></div>
        <div className="stat-row"><span className="muted">Android</span><b>Chrome <span className="mono">/field</span> or Flutter <span className="mono">mobile/</span> — stills to Azure RDD + IMU.</b></div>
        <div className="stat-row"><span className="muted">iPhone</span><b>Safari <span className="mono">/field</span> — PIN, stills to Azure RDD. Boxes on the lens.</b></div>
        <div className="stat-row"><span className="muted">Map</span><b>{s.azure_maps_enabled ? "Azure Maps road tiles via server proxy. Leaflet only draws the pins." : "Leaflet + OSM fallback — Azure Maps key not set on this host."}</b></div>
        <p className="muted" style={{ fontSize: 12, margin: "10px 0 0" }}>Tiny UI change? Run <span className="mono">scripts/ship-ui.ps1</span>. Full <span className="mono">azd up</span> is only for infra. Last UI deploy is minutes, not an hour.</p>
      </div>

      <div className="usp-strip is-confirmed" role="status" style={{ marginBottom: 12 }}>
        <div className="usp-strip-kicker">{t("uspKicker")}</div>
        <p className="usp-strip-line">{t("uspLine")}</p>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>One bus opens an UNVERIFIED first sighting. A different bus on the same 40 m / 6 h cluster is the only automatic confirm. Three later buses that do not re-sense expire a rumour. Two later buses after repair are the auditor.</p>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <h4>RDD eval <HonestyChip status={s.rdd_eval?.honesty || "EXPERIMENTAL"} compact /></h4>
        <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>{s.rdd_eval?.note || s.rdd_eval?.dataset}</p>
        <div className="stat-row"><span className="muted">Cloud infer (this App Service)</span><b>{ai?.road_damage?.honesty || "…"} · {ai?.road_damage?.runtime || "onnxruntime-cpu"}</b></div>
        <div className="stat-row"><span className="muted">Evaluated on this host</span><b>{s.rdd_eval?.evaluated ? "yes" : "no"}</b></div>
        <div className="stat-row"><span className="muted">Dataset</span><b>{s.rdd_eval?.dataset || "RDD2022 India"}</b></div>
        {s.rdd_eval?.split?.val != null && (
          <div className="stat-row"><span className="muted">Holdout</span><b>train {s.rdd_eval.split.train} · val {s.rdd_eval.split.val}{s.rdd_eval.split.test != null ? ` · test ${s.rdd_eval.split.test}` : ""} · seed {s.rdd_eval.split.seed}</b></div>
        )}
        {s.rdd_eval?.map50 != null && (
          <div className="stat-row"><span className="muted">Our India {s.rdd_eval.eval_split || "val"} mAP@0.5</span><b>{Number(s.rdd_eval.map50).toFixed(3)}</b></div>
        )}
        {s.rdd_eval?.map50_95 != null && (
          <div className="stat-row"><span className="muted">Our India {s.rdd_eval.eval_split || "val"} mAP@0.5:0.95</span><b>{Number(s.rdd_eval.map50_95).toFixed(3)}</b></div>
        )}
        {(s.rdd_eval?.classes || []).map((row) => (
          <div className="stat-row" key={row.id || row.name}>
            <span className="muted">{row.id} {row.name}</span>
            <b>{row.maps_to}{row.map50 != null ? ` · mAP@0.5 ${Number(row.map50).toFixed(3)}` : ""}</b>
          </div>
        ))}
        <p className="muted" style={{ fontSize: 12, margin: "10px 0 0" }}>Train with <span className="mono">python scripts/train_rdd.py</span>. We do not print a GitHub rival&apos;s mAP as ours.</p>
      </div>

      <div className="card" style={{marginBottom:12}}>
        <h4>{t("edgeTitle")} <HonestyChip status="RULE_BASED" compact /></h4>
        <p className="muted" style={{fontSize:12,margin:"0 0 10px"}}>{t("edgeSub")} HIGH / MED / LOW already exist as processing modes — we surface them, we do not invent federated learning.</p>
        <div className="edge-mode">
          {[
            ["HIGH","EDGE_AI","Phone overlay: WASM, WebGPU only if ORT attaches. Azure stills on CPU ONNX. No App Service GPU."],
            ["MED","LIGHTWEIGHT_EDGE_AI","Azure RDD stills only"],
            ["LOW","CAPTURE_AND_SENSOR","IMU+GPS JSON. Camera stills still go to Azure RDD."],
          ].map(([tier, mode, note]) => {
            const n = nodes.filter((x) => String(x.processing_mode||"").toUpperCase() === mode).length;
            return (
              <div key={tier} className="card-pad-sm" style={{border:"1px solid var(--line)",borderRadius:10,background:"var(--surface-2)"}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                  <b style={{fontSize:13}}>{tier}</b>
                  <span className="tag info table-num">{n} nodes</span>
                </div>
                <div className="mono muted" style={{fontSize:11,marginTop:6}}>{mode}</div>
                <div className="muted" style={{fontSize:12,marginTop:6}}>{note}</div>
              </div>
            );
          })}
        </div>
        {nodes.slice(0,6).map((n) => {
          const em = edgeModeFromProcessing(n.processing_mode);
          return (
            <div className="stat-row" key={n.id}>
              <span><b>{n.bus_code || n.code}</b> <span className="muted">{n.processing_mode}</span></span>
              <span className="tag rule">{em.tier}</span>
            </div>
          );
        })}
      </div>

      <div className="card">
        <h4>AI engines — every payload carries ai_status <span className="tag info" style={{fontSize:11}}>{ai ? Object.keys(ai).length : 0} engines</span></h4>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))",gap:10,marginTop:10}}>
          {ai ? Object.entries(ai).filter(([,v])=>v && typeof v==="object" && !Array.isArray(v) && (v.ai_status||v.honesty||v.status)).sort(([,a],[,b])=>{ const order={REAL:0,RULE_BASED:1,EXPERIMENTAL:2,SIMULATED:3,DISABLED:4}; const sa=a?.ai_status||a?.honesty||a?.status||"SIMULATED"; const sb=b?.ai_status||b?.honesty||b?.status||"SIMULATED"; return (order[sa]??99)-(order[sb]??99); }).map(([k,v])=>(
            <div key={k} style={{border:"1px solid var(--line)",borderRadius:12,padding:"10px 12px",background:"var(--surface-2)"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><b style={{fontSize:12}}>{k}</b><Pill status={v?.ai_status||v?.honesty||v?.status||"SIMULATED"} /></div>
              <div className="mono muted" style={{fontSize:11,marginTop:6,wordBreak:"break-all"}}>{v?.model||v?.note||JSON.stringify(v).slice(0,120)}</div>
              {v?.limitation && <div className="muted" style={{fontSize:11,marginTop:4}}>{v.limitation}</div>}
            </div>
          )) : <Empty icon="⚙" title="No AI capabilities" description="AI engine status will appear here" />}
        </div>
        <p className="muted" style={{fontSize:11,marginTop:10}}>REAL = neural forward pass executed • RULE_BASED = deterministic on real signals • EXPERIMENTAL = runs but not trustworthy (speed uncalibrated, Turkish signs disabled) • SIMULATED = mock/demo.</p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginTop:12}}>
        <div className="card">
          <h4>Fusion & health tuning</h4>
          <div style={{display:"grid",gap:8,marginTop:8}}>
            {[
              ["FUSION_MAX_DISTANCE_METERS","40m — spatial cluster"],
              ["FUSION_MAX_TIME_SECONDS","21600s (6h) — temporal window"],
              ["CLEAR_PASS_EXPIRE_AFTER","3 independent later buses — expire first sighting"],
              ["CLEAR_PASS_REPAIR_AFTER","2 independent later buses — fleet repair audit"],
              ["HEALTH_DEFECT_PENALTY","8 — per active defect"],
              ["HEALTH_SEVERITY_HIGH","12 — HIGH/CRITICAL extra"],
              ["BRIDGE_GEOFENCE","70m — GPS drift tolerant"],
            ].map(([k,desc])=>(
              <div key={k} style={{display:"flex",justifyContent:"space-between",padding:"8px 10px",border:"1px solid var(--line)",borderRadius:10,background:"var(--surface-2)"}}>
                <span className="mono" style={{fontSize:11,fontWeight:700}}>{k}</span><span className="muted table-num" style={{fontSize:11}}>{desc}</span>
              </div>
            ))}
          </div>
          <p className="muted" style={{fontSize:11,marginTop:8}}>Change via <span className="mono">.env</span> then restart backend. Fusion reason is stored per event.</p>
        </div>

        <div className="card">
          <h4>SHM & privacy</h4>
          <div className="mono" style={{fontSize:11,lineHeight:1.7,background:"var(--surface-2)",padding:10,borderRadius:10,border:"1px solid var(--line)"}}>
            bridge_shm.py: EMA 0.92/0.08 • ratio≥1.6 HIGH • crest≥4.5 joint • freq shift≥0.9Hz<br/>
            evidence: restricted + blur_faces/plates (pipeline planned)<br/>
            bandwidth: ~1KB JSON / observation • no video upload
          </div>
          <div style={{marginTop:10,background:"var(--surface-2)",border:"1px solid var(--line)",borderRadius:10,padding:"10px 12px"}}><h4>Raw settings JSON</h4><pre style={{margin:0,whiteSpace:"pre-wrap",wordBreak:"break-all",fontSize:11}}>{JSON.stringify(s,null,2)}</pre></div>
        </div>
      </div>

      <div className="card" style={{marginTop:12}}>
        <h4>Bridge SHM note</h4>
        <p className="muted" style={{fontSize:12,margin:0}}>Phone accel is RULE_BASED crowd SHM, not certified structural analysis. EMA baseline adapts slowly; CRITICAL auto-creates WO-BR-*. For jury: show ITO vs AIIMS history sparkline on Bridge SHM page.</p>
      </div>
    </div>
  );
}
