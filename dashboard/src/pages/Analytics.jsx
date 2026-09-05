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
  const [delay, setDelay] = useState([]);
  const [od, setOd] = useState([]);
  const [heat, setHeat] = useState([]);
  useEffect(() => {
    api("/analytics/events-by-type").then(setByType);
    api("/analytics/events-by-severity").then(setBySev);
    api("/analytics/events-over-time").then(setOver);
    api("/analytics/route-delay").then(setDelay);
    api("/analytics/od").then(setOd).catch(() => setOd([]));
    api("/analytics/heatmap").then(setHeat).catch(()=>setHeat([]));
  }, []);
  return (
    <div>
      <div className="page-header"><div><div className="crumbs">ICCC • {t("analytics").toUpperCase()}</div><h2 className="page-title">{t("pageAn")}</h2><p className="page-sub muted">{t("pageAnSub")} <span role="status"><span className="table-num">{delay.length}</span> routes • <span className="table-num">{heat.length}</span> heat • <span className="table-num">{od.length}</span> OD</span></p></div><div className="filters"><HonestyChip status="RULE_BASED" compact /><HonestyChip status="SIMULATED" compact /><span className="tag info"><span className="table-num">{delay.length}</span> routes</span><span className="tag info"><span className="table-num">{heat.length}</span> heat</span><span className="tag info"><span className="table-num">{od.length}</span> OD</span></div></div>

      <div className="truth-bar" role="status">
        <b>Honesty.</b> Heatmap is REAL-derived from fused events. OD and route-delay are SIMULATED until AVL. This is not live city traffic.
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

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginTop:12}}>
        <div className="table-wrap">
          <div className="table-toolbar"><h4 style={{margin:0}}>{t("routeDelay")}</h4><span className="muted" style={{fontSize:11}} role="status"><span className="table-num">{delay.length}</span> routes</span></div>
          <p className="muted" style={{fontSize:11,margin:"8px 14px 0"}}>From <span className="mono">trips</span> table; actual = ended_at − started_at. Missing AVL → labelled SIMULATED.</p>
          <div style={{overflow:"auto",maxHeight:260}}>
            <table>
              <thead><tr><th>Route</th><th>Planned</th><th>Actual</th><th>Delay</th><th></th></tr></thead>
              <tbody>{delay.map((d,i)=>(<tr key={i}><td className="mono" style={{fontSize:12}}>{d.route_code}</td><td className="table-num">{d.planned_duration_minutes}m</td><td className="table-num">{d.actual_duration_minutes}m</td><td className="table-num" style={{color:d.delay_minutes>0?"var(--danger)":"var(--accent-700)",fontWeight:700}}>{d.delay_minutes>0?`+${d.delay_minutes}`:d.delay_minutes}m</td><td>{d.simulated?<span className="tag sim" style={{fontSize:10}}>SIMULATED</span>:null}</td></tr>))}</tbody>
            </table>
            {delay.length===0 && <Empty icon="◷" title="No route data" description="Planned vs actual delay will appear once trips are recorded." />}
          </div>
        </div>

        <div className="table-wrap">
          <div className="table-toolbar"><h4 style={{margin:0}}>{t("heatPts")}</h4><span className="muted" style={{fontSize:11}} role="status"><span className="table-num">{heat.length}</span> points</span></div>
          <p className="muted" style={{fontSize:11,margin:"8px 14px 0"}}><span className="mono">/analytics/heatmap</span> weighted by severity + recurrence • feed to Leaflet heat layer later</p>
          <div style={{overflow:"auto",maxHeight:260}}>
            <table>
              <thead><tr><th>Lat</th><th>Lon</th><th>Weight</th></tr></thead>
              <tbody>{heat.slice(0,12).map((h,i)=>(<tr key={i}><td className="mono table-num" style={{fontSize:11}}>{heatCoord(h.lat ?? h.latitude)}</td><td className="mono table-num" style={{fontSize:11}}>{heatCoord(h.lng ?? h.lon ?? h.longitude)}</td><td className="table-num"><span className="tag info" style={{fontSize:11}}>{Number(h.weight||h.intensity||0).toFixed(1)}</span></td></tr>))}</tbody>
            </table>
            {heat.length===0 && <Empty icon="◎" title="No heat points yet" description="Emit TRAFFIC_CONGESTION events." />}
          </div>
        </div>
      </div>

      <div className="table-wrap" style={{ marginTop: 12 }}>
        <div className="table-toolbar"><h4 style={{margin:0}}>{t("odTitle")}</h4><span className="muted" style={{fontSize:11}} role="status"><span className="table-num">{od.length}</span> pairs</span></div>
        <p className="muted" style={{fontSize:11,margin:"8px 14px 0"}}>Derived from trip records + route polyline endpoints. No passenger data fabricated — empty when no trips.</p>
        <div style={{overflow:"auto"}}>
          <table>
            <thead><tr><th>Route</th><th>Origin (lat,lon)</th><th>Destination (lat,lon)</th><th>Trips</th><th></th></tr></thead>
            <tbody>{od.map((d,i)=>(<tr key={i}><td className="mono" style={{fontSize:12}}>{d.route_code}</td><td className="mono table-num" style={{fontSize:11}}>{d.origin}</td><td className="mono table-num" style={{fontSize:11}}>{d.destination}</td><td className="table-num">{d.trips}</td><td>{d.simulated?<span className="tag sim" style={{fontSize:10}}>SIMULATED</span>:null}</td></tr>))}</tbody>
          </table>
          {od.length===0 && <Empty icon="⇄" title="No trips yet" description="No trips recorded yet — start a trip from the phone." />}
        </div>
      </div>
    </div>
  );
}
