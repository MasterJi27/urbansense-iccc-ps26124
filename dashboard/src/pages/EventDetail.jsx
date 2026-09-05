import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { CircleMarker } from "react-leaflet";
import { api } from "../api";
import { useToast } from "../components/Toast.jsx";
import HonestyChip from "../components/HonestyChip.jsx";
import ConfirmationStrip from "../components/ConfirmationStrip.jsx";
import CorridorMap from "../components/CorridorMap.jsx";
import EvidenceStill from "../components/EvidenceStill.jsx";
import { useUi } from "../i18n.jsx";
import { canRevealPlate, delhiZone, dualHonesty, maskPlate, patrolLabel, uniqueSources } from "../honesty.js";

function fmtTime(ts) {
  try { return new Date(ts).toLocaleTimeString("en-GB", { hour12: false }); }
  catch { return ""; }
}
function fmtCoord(v) { return v == null ? "—" : Number(v).toFixed(5); }
function fmtScore(v) { return v == null ? "—" : `${(v * 100).toFixed(0)}%`; }
function hasValue(v) {
  if (v == null) return false;
  const s = String(v).trim();
  return Boolean(s) && s !== "—" && s !== "-" && s !== "---";
}
function stillUrl(ev) {
  if (ev?.evidence_url) return ev.evidence_url;
  const obs = (ev?.observations || []).find((o) => o.evidence_url);
  return obs?.evidence_url || "";
}

export default function EventDetail() {
  const { id } = useParams();
  const { t } = useUi();
  const [ev, setEv] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [err, setErr] = useState("");
  const [plateOpen, setPlateOpen] = useState(false);
  const toast = useToast();
  const role = (localStorage.getItem("urbansense_role") || "OPERATOR").toUpperCase();

  function load() {
    api(`/events/${id}`).then(setEv).catch((e) => setErr(e.message));
    api(`/events/${id}/ledger`).then(setLedger).catch(() => setLedger(null));
  }
  useEffect(load, [id]);

  async function act(path, body = {}) {
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      toast.success("Saved");
      load();
    } catch (e) {
      toast.error(e.message);
    }
  }
  async function createWo() {
    try {
      await api("/work-orders", { method: "POST", body: JSON.stringify({ event_id: ev.id, title: `Repair ${ev.event_type} — ${ev.public_code}` }) });
      toast.success("Work order created");
      load();
    } catch (e) {
      toast.error(e.message);
    }
  }

  function plateRaw() { return (ev?.observations || []).find((o) => o.plate_text); }
  function plateText() {
    const obs = plateRaw();
    if (!obs) return "No plate on this event";
    const conf = `${Math.round((obs.plate_confidence || 0) * 100)}% OCR`;
    if (!plateOpen) return `${maskPlate(obs.plate_text)} (${conf})`;
    return `${obs.plate_text} (${conf})`;
  }
  function speedText() {
    const kmh = (ev?.extra || {}).speed_kmh;
    if (kmh == null) return "";
    const cal = (ev?.extra || {}).speed_calibrated;
    return `${Number(kmh).toFixed(0)} km/h ${cal ? "calibrated" : "EXPERIMENTAL, uncalibrated"}`;
  }

  if (err) return <p className="err">{err}</p>;
  if (!ev) return <p className="muted">Loading event…</p>;

  const honesty = dualHonesty(ev);
  const locn = delhiZone(ev.latitude, ev.longitude);
  const buses = uniqueSources(ev);
  const timeline = (ev.observations || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const extra = ev.extra || {};
  const isOther = ev.event_type === "OTHER";
  const still = stillUrl(ev);
  const title = isOther ? "Unclassified still" : ev.event_type.replaceAll("_", " ");
  const fusionNote = isOther
    ? t("uspOther")
    : (ev.fusion_reason || "Single observation — no merge yet.");

  return (
    <div className="incident-pack">
      <div className="print-only incident-pack-head">
        <h1>UrbanSense incident pack</h1>
        <p>ASSISTS AUTHORITIES — DOES NOT ACCUSE</p>
        <p>{ev.public_code} · {ev.event_type} · {ev.status}</p>
      </div>
      <div className="case-head no-print">
        <div>
          <div className="crumbs"><Link to="/events">Events</Link> · {ev.public_code}</div>
          <h2 className="page-title">{title}</h2>
          <p className="page-sub muted">
            {isOther
              ? "Phone or CCTV still. No compatible road-defect label. Not a pothole claim."
              : `${locn.zone} · ${locn.ward} · ${buses[0] || "source unknown"} · ${ev.timestamp ? new Date(ev.timestamp).toLocaleString() : "—"}`}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <HonestyChip event={ev} />
          {extra.department_desk && (
            <span className="tag rule" title={extra.department_note || extra.department_honesty}>
              {t("deptChip")}: {extra.department_desk}
            </span>
          )}
          {extra.bbox_frac != null && (
            <span className="tag rule" title={extra.severity_honesty || "RULE_BASED"}>
              Box area {(Number(extra.bbox_frac) * 100).toFixed(1)}% · {ev.severity}
            </span>
          )}
          <span className={`badge ${ev.severity}`}>{ev.severity}</span>
          <span className={`badge ${ev.status}`}>{ev.status}</span>
          <button className="btn ghost no-print" type="button" onClick={() => window.print()}>Print incident pack</button>
        </div>
      </div>

      <ConfirmationStrip event={ev} ledger={ledger} />

      <div className="card incident-pack-facts" style={{ marginBottom: 12 }}>
        <h4>Incident facts</h4>
        <table><tbody>
          {[
            ["Public code", ev.public_code],
            ["GPS", `${fmtCoord(ev.latitude)}, ${fmtCoord(ev.longitude)}`],
            ["Time", ev.timestamp ? new Date(ev.timestamp).toLocaleString() : ""],
            ["Zone", `${locn.zone} · ${locn.ward}`],
            ["Source", ev.source_id],
            ["Camera bay", extra.camera_bay],
            ["Method", extra.method],
            ["Desk", extra.department_desk],
            ["Routing", extra.department_honesty === "RULE_BASED" ? "RULE_BASED department map" : extra.department_honesty],
            ["Honesty", `${honesty.payloadLabel} payload · ${honesty.engine} engine`],
            ["Azure caption", extra.caption],
            ["Plate (masked)", plateRaw() ? maskPlate(plateRaw().plate_text) : ""],
            ["Line", "ASSISTS AUTHORITIES — DOES NOT ACCUSE"],
          ].filter(([, v]) => hasValue(v)).map(([k, v]) => (
            <tr key={k}><td style={{ fontWeight: 700, width: 160 }}>{k}</td><td className="mono" style={{ fontSize: 12 }}>{v}</td></tr>
          ))}
        </tbody></table>
      </div>

      {honesty.seed && (
        <div className="truth-bar" role="status">
          <b>SEED row.</b>
          This record was inserted for the demo. The engine for {ev.event_type} is {honesty.engine}.
          Fusion and VERIFY still run on real backend code.
        </div>
      )}

      <div className="ops-grid">
        <div>
          <div className="card">
            <h4>How this became one event</h4>
            <p style={{ fontSize: 14, lineHeight: 1.55, margin: "0 0 12px" }}>{fusionNote}</p>
            <div className="stat-row"><span className="muted">Observations</span><b className="table-num">{ev.observation_count ?? timeline.length}</b></div>
            <div className="stat-row"><span className="muted">Patrol</span><b>{isOther ? t("patrolOther") : patrolLabel(ev)}</b></div>
            <div className="stat-row"><span className="muted">Sources</span><b className="table-num">{ev.source_count ?? buses.length}</b></div>
            <div className="stat-row"><span className="muted">Evidence score</span><b className="table-num">{ev.confidence == null ? "—" : Number(ev.confidence).toFixed(2)}</b></div>
            <p className="muted" style={{ fontSize: 12, margin: "8px 0 0" }}>Score is max(confidence) + diversity. It is not certainty.</p>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h4>What the software actually did</h4>
            <table><tbody>
              {[
                ["Payload", honesty.payloadLabel],
                ["Engine", honesty.engine],
                ["Method", extra.method],
                ["Model", extra.model && extra.model !== "none" && extra.model !== "yolo" ? extra.model : null],
                ["Derivation", extra.derivation],
                ["Azure caption", extra.caption],
                ["Azure tags", Array.isArray(extra.azure_tags) && extra.azure_tags.length ? extra.azure_tags.join(", ") : null],
                ["Camera bay", extra.camera_bay],
                ["Patrol", extra.patrol_note || patrolLabel(ev)],
                ["Confirming buses", Array.isArray(extra.confirming_sources) && extra.confirming_sources.length ? extra.confirming_sources.join(", ") : null],
                ["Officer brief", extra.officer_brief],
                ["Brief model", extra.officer_brief_model],
                ["Plate", plateRaw() ? plateText() : null],
                ["Speed", speedText() || null],
              ].filter(([, v]) => hasValue(v)).map(([k, v]) => (
                <tr key={k}><td style={{ fontWeight: 700, width: 140 }}>{k}</td><td className="mono" style={{ fontSize: 12 }}>{v}</td></tr>
              ))}
            </tbody></table>
            {plateRaw() && (
              canRevealPlate(role) ? (
                <button className="btn ghost" type="button" onClick={() => setPlateOpen((v) => !v)}>{plateOpen ? t("hidePlate") : t("revealPlate")}</button>
              ) : (
                <span className="tag off">Plate locked — {role}</span>
              )
            )}
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h4>Passes</h4>
            {timeline.length === 0 && <p className="muted">No observation timeline on this event.</p>}
            <div className="timeline">
              {timeline.map((o, i) => (
                <div key={o.id} className={`tl-item ${i === timeline.length - 1 ? "active" : ""}`}>
                  <div className="title">{fmtTime(o.timestamp)} · {o.source_id} · {fmtScore(o.confidence)}</div>
                  <div className="meta">{fmtCoord(o.latitude)}, {fmtCoord(o.longitude)}</div>
                  <HonestyChip event={{ event_type: ev.event_type, simulated: o.simulated, extra: o.extra }} compact />
                </div>
              ))}
            </div>
          </div>
        </div>

        <div>
          {still ? (
            <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 12 }}>
              <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)" }}><h4 style={{ margin: 0 }}>Field still</h4></div>
              <EvidenceStill url={still} alt={`${ev.public_code} still`} />
            </div>
          ) : null}
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--line)" }}><h4 style={{ margin: 0 }}>Location</h4></div>
            {ev.latitude != null && ev.longitude != null ? (
              <CorridorMap center={[ev.latitude, ev.longitude]} zoom={15} height={260}>
                <CircleMarker center={[ev.latitude, ev.longitude]} radius={11} pathOptions={{ color: "#b42318", fillColor: "#b42318", fillOpacity: 0.85 }} />
              </CorridorMap>
            ) : <p className="muted" style={{ padding: 14 }}>No GPS on this event.</p>}
          </div>
        </div>
      </div>

      <div className="case-actions no-print">
        <Link to="/events" className="btn ghost">Back to events</Link>
        <button className="btn" onClick={() => act(`/events/${ev.id}/verify`, { notes: "confirmed" })}>{t("confirm")}</button>
        <button className="btn ghost" onClick={() => act(`/events/${ev.id}/reject`, { notes: "reject" })}>{t("reject")}</button>
        <button className="btn ghost" onClick={() => act(`/events/${ev.id}/reject`, { notes: "false_positive" })}>Log as false positive</button>
        <button className="btn ghost" onClick={() => act(`/events/${ev.id}/brief`)}>Draft Azure OpenAI brief</button>
        <button className="btn ghost" onClick={createWo}>{t("createWo")}</button>
      </div>
    </div>
  );
}
