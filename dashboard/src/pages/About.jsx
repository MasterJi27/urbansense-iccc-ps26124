import { useEffect, useState } from "react";
import { api } from "../api";
import DemoTruth from "../components/DemoTruth.jsx";
import HonestGaps from "../components/HonestGaps.jsx";
import { useUi } from "../i18n.jsx";

function statusClass(status) {
  if (status === "REAL") return "real";
  if (status === "RULE_BASED") return "rule";
  if (status === "DISABLED") return "off";
  return "sim";
}

export default function About() {
  const { t } = useUi();
  const [events, setEvents] = useState([]);
  const [realEngines, setRealEngines] = useState(null);
  const [ai, setAi] = useState(null);
  const [ps, setPs] = useState(null);

  useEffect(() => {
    api("/events?limit=80").then((e) => setEvents(Array.isArray(e) ? e : [])).catch(() => setEvents([]));
    api("/ai/capabilities").then((caps) => {
      setAi(caps);
      if (caps) setRealEngines(Object.values(caps).filter((v) => v && v.ai_status === "REAL").length);
    }).catch(() => setAi(null));
    api("/ai/ps26124").then(setPs).catch(() => setPs(null));
  }, []);

  const engines = ai
    ? Object.entries(ai).filter(([, v]) => v && typeof v === "object" && !Array.isArray(v) && (v.ai_status || v.honesty || v.status))
    : [];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="crumbs">ICCC &gt; {t("about").toUpperCase()}</div>
          <h2 className="page-title">{t("pageAbout")}</h2>
          <p className="page-sub muted">{t("pageAboutSub")}</p>
        </div>
      </div>

      <DemoTruth events={events} realEngines={realEngines} />

      <div className="usp-strip is-confirmed" role="status" style={{ marginBottom: 12 }}>
        <div className="usp-strip-kicker">{t("uspKicker")}</div>
        <p className="usp-strip-line">{t("uspLine")}</p>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
          One bus opens an UNVERIFIED first sighting. A different bus on the same 40 m / 6 h cluster is the only automatic confirm.
          Three later buses that do not re-sense expire a rumour. Two later buses after repair are the auditor.
          Composio is mail on FLEET_CONFIRMED only.
        </p>
      </div>

      <HonestGaps />

      {ps && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h4>BEL PS 26124</h4>
          <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>{ps.note}</p>
          <div className="stat-row"><span className="muted">Camera bays</span><b className="mono" style={{ fontSize: 12 }}>{(ps.camera_bays || []).join(" · ")}</b></div>
          <div className="stat-row"><span className="muted">Coverage</span><b className="table-num">{Object.entries(ps.counts || {}).map(([k, v]) => `${v} ${k}`).join(" · ")}</b></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 10 }}>
            {(ps.items || []).filter((row) => row.status === "REAL" || row.status === "RULE_BASED" || row.status === "DISABLED").map((row) => (
              <div key={row.id} className="stat-row" style={{ margin: 0 }}>
                <span style={{ fontSize: 12 }}>{row.requirement}</span>
                <span className={`tag ${statusClass(row.status)}`} style={{ fontSize: 10 }}>{row.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="cards" style={{ marginBottom: 12 }}>
        <div className="card">
          <h4>{t("juryTitle")}</h4>
          <div className="stat-row"><span><b>{t("jury1t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury1m")}</div></span></div>
          <div className="stat-row"><span><b>{t("jury2t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury2m")}</div></span></div>
          <div className="stat-row"><span><b>{t("jury3t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury3m")}</div></span></div>
          <div className="stat-row"><span><b>{t("jury4t")}</b><div className="muted" style={{ fontSize: 12 }}>{t("jury4m")}</div></span></div>
        </div>
        <div className="card">
          <h4>{t("evidenceG")}</h4>
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>{t("evidenceP")}</p>
          <p className="muted" style={{ fontSize: 12, margin: "10px 0 0" }}>{t("dpdpBanner")}</p>
        </div>
      </div>

      <div className="card">
        <h4>AI engines — every payload carries ai_status <span className="tag info" style={{ fontSize: 11 }}>{engines.length} engines</span></h4>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 10, marginTop: 10 }}>
          {engines.sort(([, a], [, b]) => {
            const order = { REAL: 0, RULE_BASED: 1, EXPERIMENTAL: 2, SIMULATED: 3, DISABLED: 4 };
            const sa = a?.ai_status || a?.honesty || a?.status || "SIMULATED";
            const sb = b?.ai_status || b?.honesty || b?.status || "SIMULATED";
            return (order[sa] ?? 99) - (order[sb] ?? 99);
          }).map(([k, v]) => {
            const status = v?.ai_status || v?.honesty || v?.status || "SIMULATED";
            return (
              <div key={k} style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "10px 12px", background: "var(--surface-2)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b style={{ fontSize: 12 }}>{k}</b>
                  <span className={`tag ${statusClass(status)}`} style={{ fontSize: 11, fontWeight: 700 }}>{status}</span>
                </div>
                <div className="mono muted" style={{ fontSize: 11, marginTop: 6, wordBreak: "break-all" }}>{v?.model || v?.note || JSON.stringify(v).slice(0, 120)}</div>
                {v?.limitation && <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{v.limitation}</div>}
              </div>
            );
          })}
        </div>
        <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
          REAL = neural forward pass executed • RULE_BASED = deterministic on real signals • EXPERIMENTAL = runs but not trustworthy • SIMULATED = mock/demo.
          Phone overlay is WASM. Official ticket is the Azure still. Not 1 ms Azure RTT.
        </p>
      </div>
    </div>
  );
}
