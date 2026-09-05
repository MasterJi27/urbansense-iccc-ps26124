import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";
import { api } from "../api";
import Empty from "../components/Empty.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import { useUi } from "../i18n.jsx";

function heatCoord(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(4) : "—";
}

export default function Analytics() {
  const { t } = useUi();
  const [byType, setByType] = useState([]);
  const [bySev, setBySev] = useState([]);
  const [over, setOver] = useState([]);
  const [heat, setHeat] = useState([]);
  useEffect(() => {
    api("/analytics/events-by-type").then(setByType);
    api("/analytics/events-by-severity").then(setBySev);
    api("/analytics/events-over-time").then(setOver);
    api("/analytics/heatmap").then(setHeat).catch(()=>setHeat([]));
  }, []);
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">ICCC • {t("analytics").toUpperCase()}</div><h2 className="page-title">{t("pageAn")}</h2><p className="page-sub muted">{t("pageAnSub")} <span role="status"><span className="table-num">{heat.length}</span> heat points</span></p></div><div className="filters"><HonestyChip status="REAL" compact /><span className="tag info"><span className="table-num">{heat.length}</span> heat</span></div></div>

      <div className="truth-bar" role="status">
        <b>Live counts only.</b> Charts and heatmap come from fused events. Route-delay and OD need a real AVL feed — they are not shown.
      </div>

      <div className="row">
        <div className="card">
          <h4>Events by type</h4>
          {byType.length === 0 ? (
            <Empty icon="▦" title="No events yet" description="Events by type will appear here" />
          ) : (
            <div role="img" aria-label="Events by type bar chart">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byType}>
                <XAxis dataKey="type" tick={{ fill: "var(--muted)", fontSize: 10 }} interval={0} angle={-18} dy={10} height={50}/>
                <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 10 }} />
                <Bar dataKey="count" fill="var(--accent)" radius={[8,8,0,0]} />
              </BarChart>
            </ResponsiveContainer>
            </div>
          )}
        </div>
        <div className="card">
          <h4>By severity</h4>
          {bySev.length === 0 ? (
            <Empty icon="◉" title="No severity data" description="Severity breakdown will appear here" />
          ) : (
            <div role="img" aria-label="Events by severity bar chart">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={bySev}>
                <XAxis dataKey="severity" tick={{ fill: "var(--muted)", fontSize: 10 }} />
                <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 10 }} />
                <Bar dataKey="count" fill="var(--info)" radius={[8,8,0,0]} />
              </BarChart>
            </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h4>Over time</h4>
        {over.length === 0 ? (
          <Empty icon="◐" title="No timeline data" description="Event trend over time will appear here" />
        ) : (
          <div role="img" aria-label="Events over time line chart">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={over}>
              <XAxis dataKey="date" tick={{ fill: "var(--muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 10 }} />
              <Line dataKey="count" stroke="var(--warn)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="table-wrap" style={{ marginTop: 12 }}>
        <div className="table-toolbar"><h4 style={{margin:0}}>{t("heatPts")}</h4><span className="muted" style={{fontSize:11}} role="status"><span className="table-num">{heat.length}</span> points</span></div>
        <p className="muted" style={{fontSize:11,margin:"8px 14px 0"}}>Weighted by severity + recurrence from fused events.</p>
        <div style={{overflow:"auto",maxHeight:260}}>
          <table>
            <thead><tr><th>Lat</th><th>Lon</th><th>Weight</th></tr></thead>
            <tbody>{heat.slice(0,12).map((h,i)=>(<tr key={i}><td className="mono table-num" style={{fontSize:11}}>{heatCoord(h.lat ?? h.latitude)}</td><td className="mono table-num" style={{fontSize:11}}>{heatCoord(h.lng ?? h.lon ?? h.longitude)}</td><td className="table-num"><span className="tag info" style={{fontSize:11}}>{Number(h.weight||h.intensity||0).toFixed(1)}</span></td></tr>))}</tbody>
          </table>
          {heat.length===0 && <Empty icon="◎" title="No heat points yet" description="Phone detections will appear here after fusion." />}
        </div>
      </div>
    </div>
  );
}
