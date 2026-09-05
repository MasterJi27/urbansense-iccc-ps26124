import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken } from "../api";
import HonestyChip from "../components/HonestyChip.jsx";
import { useUi } from "../i18n.jsx";
import DemoTruth from "../components/DemoTruth.jsx";
import { dualHonesty, isMonsoon, isVru, patrolLabel } from "../honesty.js";
import { mergeEventRow, openAuthedSocket, pollJson } from "../live/deskLive.js";

export default function Events() {
  const { t, monsoon, setMonsoon, vru, setVru } = useUi();
  const [rows, setRows] = useState([]);
  const [citizenOpen, setCitizenOpen] = useState(false);
  const [citizenType, setCitizenType] = useState("ROAD_OBSTRUCTION");
  const [citizenNote, setCitizenNote] = useState("");
  const [citizenBusy, setCitizenBusy] = useState(false);
  const [q, setQ] = useState("");
  const [sev, setSev] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [typeF, setTypeF] = useState("ALL");
  const [sort, setSort] = useState("recent");
  const [err, setErr] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [hideSeed, setHideSeed] = useState(true);
  useEffect(() => {
    setErr("");
    api("/events?limit=300").then(setRows).catch((e) => setErr(e.message || "Failed to load events"));
    const token = getToken();
    const stopWs = openAuthedSocket("/ws/events", token, (m) => {
      try {
        const msg = JSON.parse(m.data);
        if (msg.event) setRows((prev) => mergeEventRow(prev, msg.event, 300));
      } catch { /* ignore bad frames */ }
    });
    const stopPoll = pollJson("/events?limit=300", (e) => {
      if (Array.isArray(e)) setRows(e);
    }, 2000);
    return () => {
      stopWs();
      stopPoll();
    };
  }, [retryKey]);

  const filtered = useMemo(()=>{
    let r=[...rows];
    if(q) r=r.filter(e=>`${e.public_code} ${e.event_type} ${e.status} ${e.severity}`.toLowerCase().includes(q.toLowerCase()));
    if(sev!=="ALL") r=r.filter(e=>e.severity===sev);
    if(status!=="ALL") r=r.filter(e=>e.status===status);
    if(typeF!=="ALL") r=r.filter(e=>e.event_type===typeF);
    r = r.filter((e) => e.event_type !== "WATERLOGGING");
    if (hideSeed) r = r.filter((e) => !dualHonesty(e).seed);
    if (vru || monsoon) r = r.filter((e) => (vru && isVru(e)) || (monsoon && isMonsoon(e)));
    if(sort==="score") r.sort((a,b)=>b.confidence-a.confidence);
    else if(sort==="obs") r.sort((a,b)=>b.observation_count-a.observation_count);
    else r.sort((a,b)=> new Date(b.updated_at||b.created_at) - new Date(a.updated_at||a.created_at));
    return r;
  },[rows,q,sev,status,typeF,sort,vru,monsoon,hideSeed]);

  async function submitCitizen() {
    if (citizenBusy) return;
    setCitizenBusy(true);
    setErr("");
    try {
      await api("/observations", {
        method: "POST",
        body: JSON.stringify({
          event_type: citizenType,
          severity: citizenType === "WATERLOGGING" ? "HIGH" : "MEDIUM",
          latitude: 28.6139,
          longitude: 77.209,
          source_type: "INSPECTOR",
          source_id: `inspector:${localStorage.getItem("urbansense_name") || "ops"}`,
          confidence: 0.7,
          simulated: citizenType === "WATERLOGGING",
          extra: {
            ai_status: citizenType === "WATERLOGGING" ? "SIMULATED" : "RULE_BASED",
            engine_status: citizenType === "WATERLOGGING" ? "SIMULATED" : "RULE_BASED",
            payload_kind: "FIELD",
            citizen_report: true,
            citizen_description: citizenNote || "ICCC / inspector still",
            method: "human-ingest",
          },
        }),
      });
      setCitizenNote("");
      setCitizenOpen(false);
      setRetryKey((k) => k + 1);
    } catch (e) {
      setErr(e.message || "Report failed");
    } finally {
      setCitizenBusy(false);
    }
  }

  const types=[...new Set(rows.map(r=>r.event_type))].sort();
  const statuses=[...new Set(rows.map(r=>r.status))].sort();

  const allSelected = filtered.length > 0 && filtered.every((e) => selected.has(String(e.id)));
  function toggleOne(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      const k = String(id);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }
  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      const every = filtered.length > 0 && filtered.every((e) => next.has(String(e.id)));
      if (every) filtered.forEach((e) => next.delete(String(e.id)));
      else filtered.forEach((e) => next.add(String(e.id)));
      return next;
    });
  }
  function clearSelection() { setSelected(new Set()); }

  async function bulk(kind) {
    if (selected.size === 0 || busy) return;
    setBusy(true);
    setErr("");
    const ids = [...selected];
    try {
      for (const id of ids) {
        await api(`/events/${id}/${kind}`, { method: "POST", body: JSON.stringify(kind === "verify" ? { notes: "confirmed (bulk)" } : { notes: "rejected (bulk)" }) });
      }
      setSelected(new Set());
      setRetryKey((k) => k + 1);
    } catch (e) {
      setErr(e.message || `Bulk ${kind} failed`);
    } finally {
      setBusy(false);
    }
  }

  function exportCsv() {
    const esc = (v) => {
      const s = String(v ?? "");
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = ["code,type,severity,status,obs,sources,score,updated"];
    for (const e of filtered) {
      lines.push([
        e.public_code,
        e.event_type,
        e.severity,
        e.status,
        e.observation_count ?? "",
        e.source_count ?? "",
        e.confidence != null ? `${(e.confidence * 100).toFixed(0)}%` : "",
        e.updated_at || "",
      ].map(esc).join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "events.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
  if (err) return <div className="card" role="alert" style={{padding:16}}><b>Couldn't load events</b><p className="muted" style={{fontSize:12,margin:"6px 0 12px"}}>{err} — check your connection and try again.</p><button className="btn" onClick={() => setRetryKey((k) => k + 1)}>Retry</button></div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="crumbs">ICCC • {t("events").toUpperCase()}</div>
          <h2 className="page-title">{t("pageEvents")}</h2>
          <p className="page-sub muted">{t("pageEventsSub")} <span role="status"><span className="table-num">{filtered.length}</span> {t("of")} <span className="table-num">{rows.length}</span></span></p>
        </div>
        <div className="filters" role="group" aria-label="Severity filter">
          {["ALL","CRITICAL","HIGH","MEDIUM","LOW"].map(s=>(
            <button key={s} className={`chip ${sev===s?"active":""}`} onClick={()=>setSev(s)} aria-pressed={sev===s} aria-label={`Filter by ${s} severity`}>{t(s)}</button>
          ))}
          <button className={`chip ${vru?"active":""}`} onClick={()=>setVru((v)=>!v)} aria-pressed={vru}>{t("schoolZone")}</button>
          <button className={`chip ${monsoon?"active":""}`} onClick={()=>setMonsoon((v)=>!v)} aria-pressed={monsoon}>{t("monsoon")}</button>
          <span className="chip live"><span className="table-num">{rows.filter(r=>r.observation_count>1).length}</span>&nbsp;fused</span>
          <button className={`chip ${hideSeed?"active":""}`} onClick={()=>setHideSeed((v)=>!v)} aria-pressed={hideSeed}>Hide SEED rows</button>
          <button className="btn ghost" onClick={() => setCitizenOpen((v) => !v)} aria-pressed={citizenOpen}>{t("citizenStill")}</button>
          <button className="btn ghost" onClick={exportCsv} title="Export filtered rows as CSV">{t("exportCsv")}</button>
        </div>
      </div>
      <DemoTruth events={rows} />

      <div className="table-wrap">
        <div className="table-toolbar">
          <input placeholder="Search code / type / status" aria-label="Search events" value={q} onChange={e=>setQ(e.target.value)} />
          <select aria-label="Severity filter" value={sev} onChange={e=>setSev(e.target.value)}><option value="ALL">{t("allSev")}</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
          <select aria-label="Status filter" value={status} onChange={e=>setStatus(e.target.value)}><option value="ALL">{t("allStatus")}</option>{statuses.map(s=><option key={s} value={s}>{s}</option>)}</select>
          <select aria-label="Type filter" value={typeF} onChange={e=>setTypeF(e.target.value)}><option value="ALL">{t("allTypes")}</option>{types.map((tp)=><option key={tp} value={tp}>{tp}</option>)}</select>
          <select aria-label="Sort events" value={sort} onChange={e=>setSort(e.target.value)}><option value="recent">{t("recent")}</option><option value="score">{t("byScore")}</option><option value="obs">{t("byObs")}</option></select>
        </div>
        {selected.size > 0 && (
          <div className="table-toolbar" role="status" aria-live="polite" style={{gap:8,alignItems:"center"}}>
            <b className="table-num">{selected.size} selected</b>
            <button className="btn" disabled={busy} onClick={() => bulk("verify")}>{busy ? "Working…" : "Verify"}</button>
            <button className="btn ghost" disabled={busy} onClick={() => bulk("reject")}>{busy ? "Working…" : "Reject"}</button>
            <button className="btn ghost" disabled={busy} onClick={clearSelection}>Clear</button>
          </div>
        )}
        <div style={{overflow:"auto",maxHeight:"62vh"}}>
          <table>
            <thead><tr><th style={{width:32}}><input type="checkbox" aria-label="Select all events" checked={allSelected} onChange={toggleAll} /></th><th className="sticky-first" style={{position:"sticky",left:0,background:"var(--surface-2)",zIndex:2}}>{t("code")}</th><th>{t("type")}</th><th>{t("honesty")}</th><th>{t("severity")}</th><th>{t("status")}</th><th>{t("obs")}</th><th>{t("sources")}</th><th>{t("score")}</th><th>{t("updated")}</th></tr></thead>
            <tbody>
              {filtered.map((e)=>(
                <tr key={e.id}>
                  <td><input type="checkbox" aria-label={`Select ${e.public_code}`} checked={selected.has(String(e.id))} onChange={() => toggleOne(e.id)} /></td>
                  <td className="sticky-first" style={{position:"sticky",left:0,background:"var(--surface)",zIndex:1,maxWidth:240}}><Link to={`/events/${e.id}`} className="evlink" title={e.public_code || ""} style={{maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",display:"inline-block",verticalAlign:"bottom"}}>{e.public_code}</Link></td>
                  <td style={{maxWidth:260}}><span className="mono" title={e.event_type || ""} style={{fontSize:12,maxWidth:240,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",display:"inline-block",verticalAlign:"bottom"}}>{e.event_type}</span></td>
                  <td style={{minWidth:140}}><HonestyChip event={e} compact /></td>
                  <td><span className={`badge ${e.severity}`}>{e.severity}</span></td>
                  <td><span className={`badge ${e.status}`}>{e.status}</span><div className="muted" style={{ fontSize: 10 }}>{patrolLabel(e)}</div></td>
                  <td className="table-num"><b className="table-num">{e.observation_count ?? "—"}</b></td>
                  <td className="table-num">{e.source_count ?? "—"}</td>
                  <td className="table-num">{e.confidence != null ? `${(e.confidence * 100).toFixed(0)}%` : "—"}</td>
                  <td className="muted" style={{fontSize:12}}>{e.updated_at?.slice(0,16)?.replace("T"," ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length===0 && <div className="empty">No events match. Try clearing filters.</div>}
        </div>
      </div>
      {citizenOpen && (
        <div className="card" style={{marginTop:12}}>
          <h4>{t("citizenStill")}</h4>
          <p className="muted" style={{fontSize:12,margin:"0 0 8px"}}>{t("citizenHint")}</p>
          <div className="filters">
            <select aria-label="Report type" value={citizenType} onChange={(e) => setCitizenType(e.target.value)}>
              <option value="ROAD_OBSTRUCTION">ROAD_OBSTRUCTION</option>
              <option value="PEDESTRIAN_RISK">PEDESTRIAN_RISK</option>
            </select>
            <input placeholder="Ward note (optional)" aria-label="Inspector note" value={citizenNote} onChange={(e) => setCitizenNote(e.target.value)} />
            <button className="btn" disabled={citizenBusy} onClick={submitCitizen}>{citizenBusy ? "…" : t("submitReport")}</button>
          </div>
        </div>
      )}
      {monsoon && <div className="ops-banner warn" style={{marginTop:12}}><div><b>{t("monsoon")}</b>Waterlogging is a citizen/inspector workflow — never claimed as neural detection.</div></div>}
      <p className="muted" style={{fontSize:12,marginTop:8}}>Evidence score = max(confidence) + diversity bonuses — not statistical certainty. See Event Detail → Fusion for exact formula.</p>
    </div>
  );
}
