import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Empty from "../components/Empty.jsx";
import CameraBayDiagram, { bayIdsFromSensors } from "../components/CameraBayDiagram.jsx";
import { useUi } from "../i18n.jsx";

export default function Fleet() {
  const { t } = useUi();
  const [buses, setBuses] = useState([]);
  const [sensors, setSensors] = useState([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    Promise.all([api("/buses"), api("/sensor-nodes").catch(()=>[])])
      .then(([b,s])=>{ setBuses(b); setSensors(s); }).catch((e)=>setErr(e.message));
  }, []);
  const filtered = useMemo(()=> buses.filter(b=> !q || `${b.code} ${b.registration}`.toLowerCase().includes(q.toLowerCase())), [buses,q]);
  if (err) return <p className="err">{err}</p>;
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">OPERATE • {t("fleet").toUpperCase()}</div><h2 className="page-title">{t("pageFleet")}</h2><p className="page-sub muted">{t("pageFleetSub")} • <span role="status"><span className="table-num">{filtered.length}</span> {t("of")} <span className="table-num">{buses.length}</span> buses • <span className="table-num">{sensors.length}</span> sensors</span></p></div>
        <div className="filters"><input placeholder={t("searchBus")} aria-label={t("searchBus")} value={q} onChange={e=>setQ(e.target.value)} /><span className="tag info"><span className="table-num">{sensors.length}</span> sensors</span></div>
      </div>
      {filtered.length === 0 ? (
        <div className="table-wrap">
          <Empty
            icon="🚌"
            title="No buses found"
            description={q ? `No buses match “${q}”` : "No buses registered yet"}
            actionLabel={q ? "Clear search" : undefined}
            onAction={q ? () => setQ("") : undefined}
          />
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-toolbar"><span className="muted" style={{fontSize:12}} role="status"><span className="table-num">{filtered.length}</span> of <span className="table-num">{buses.length}</span> buses</span><span className="tag info"><span className="table-num">{sensors.length}</span> sensors bound</span></div>
          <div style={{overflow:"auto"}}>
            <table>
              <thead><tr><th>Bus</th><th>Registration</th><th>Route</th><th>Cameras (PS 26124)</th><th>Sensor</th><th>Mode</th><th>QR</th></tr></thead>
              <tbody>
                {filtered.map((b)=>{
                  const bound=sensors.filter(x=>x.bus_id===b.id);
                  const s=bound[0];
                  const bays=(b.camera_bays||bound).map((c)=>String(c.device_label||c.code||"").replace("BUS_CCTV_","")).filter(Boolean);
                  return (
                    <tr key={b.id}>
                      <td><span style={{display:"inline-flex",alignItems:"center",gap:8}}><span className={`status-dot ${s?.camera_status==="ONLINE"?"on":"off"}`} aria-hidden="true" /><Link to={`/map`} className="evlink">{b.code}</Link></span> {b.code==="BUS-042"?<span className="tag real" style={{marginLeft:6,fontSize:10}}>PRIMARY DEMO</span>:null}</td>
                      <td className="mono table-num" style={{fontSize:12}}>{b.registration} <span className="tag info" style={{marginLeft:6,fontSize:10}}>{b.route_code || "—"}</span></td>
                      <td className="muted table-num">{b.route_code || s?.bus_code || "—"}</td>
                      <td className="mono" style={{fontSize:10}}>{bays.length ? bays.join(" · ") : "—"}</td>
                      <td>{s ? <span className={`tag ${s.camera_status==="ONLINE"?"real":"rule"}`} style={{fontSize:11}}>{s.code}</span> : <span className="muted">unbound</span>}</td>
                      <td className="muted" style={{fontSize:11}}>{s?.processing_mode?.replaceAll("_"," ") || "—"}</td>
                      <td><span style={{display:"inline-flex",alignItems:"center",gap:6,maxWidth:260}}><span className="mono muted table-num" title={b.qr_payload} style={{fontSize:11,maxWidth:180,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{b.qr_payload}</span><button className="btn ghost btn-sm" title="Copy QR payload" style={{fontSize:10,padding:"2px 8px"}} onClick={()=>navigator.clipboard.writeText(b.qr_payload)}>Copy</button></span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="cards" style={{ marginTop: 14 }}>
        {["BUS-042", "BUS-017"].map((code) => {
          const bus = buses.find((b) => b.code === code);
          if (!bus) return null;
          const bound = sensors.filter((x) => x.bus_id === bus.id);
          return (
            <div key={code} className="card">
              <h4>{code} — five camera bays</h4>
              <p className="muted" style={{ fontSize: 12, margin: "0 0 8px" }}>Cabin never scores road defects. Frames, not raw video to cloud.</p>
              <CameraBayDiagram busCode={code} present={bayIdsFromSensors(bus.camera_bays || bound)} />
            </div>
          );
        })}
      </div>
      <p className="muted" style={{fontSize:11,marginTop:8}}>Bind phone via <span className="mono">urbansense://bus/BUS-042</span> → <span className="mono">POST /sensor-nodes/bind</span>. Heartbeat every 12s updates sensor fleet health.</p>
    </div>
  );
}
