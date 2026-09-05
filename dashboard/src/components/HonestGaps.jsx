import { useEffect, useState } from "react";
import { api } from "../api";
import { useUi } from "../i18n.jsx";

const GAPS = [
  { req: "iPhone / any-phone camera", now: "REAL", how: "Web field booth · Safari getUserMedia · same still ingest" },
  { req: "Live 4-cam NVR", now: "RULE_BASED", how: "Any-camera still bridge (/cctv). Not 24×7 NVR. Cabin cannot invent road defects." },
  { req: "Continuous YOLO on Azure", now: "DISABLED", how: "On-demand still only. No 24×7 GPU stream." },
  { req: "Waterlogging neural net", now: "RULE_BASED", how: "Human tap + GPS. Vision tags if Azure Vision is on." },
  { req: "Indian MoRTH sign model", now: "DISABLED", how: "GIS missing-sign geofence only. No Turkish/Indian classifier." },
  { req: "School-child classifier", now: "RULE_BASED", how: "School geofence + speed drop. No child detector." },
  { req: "Hit-and-run accident net", now: "RULE_BASED", how: "Speed trigger + optional still. Plate OCR on backend still." },
  { req: "Calibrated speed / AVL-OD", now: "EXPERIMENTAL", how: "Phone GPS speed uncalibrated. OD demo-flagged." },
  { req: "Field-accuracy certificate", now: "DISABLED", how: "Not claimed. Demonstration data." },
];

export default function HonestGaps() {
  const { t } = useUi();
  const [maps, setMaps] = useState(null);
  useEffect(() => {
    api("/maps/config").then(setMaps).catch(() => setMaps({ enabled: false }));
  }, []);
  const rows = [
    ...GAPS,
    {
      req: "Azure Maps corridor tiles",
      now: maps?.enabled ? "REAL" : "RULE_BASED",
      how: maps?.enabled
        ? "Server-proxied Azure Maps road tiles. Detection is not Azure Maps."
        : "OSM fallback — Azure Maps key not set. Detection is not Azure Maps.",
    },
  ];
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <h4 style={{ margin: "0 0 6px" }}>{t("gapsTitle")}</h4>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>{t("gapsSub")}</p>
      <div style={{ display: "grid", gap: 6 }}>
        {rows.map((row) => (
          <div key={row.req} className="stat-row" style={{ margin: 0, alignItems: "flex-start" }}>
            <span style={{ minWidth: 0 }}>
              <b style={{ fontSize: 12 }}>{row.req}</b>
              <div className="muted" style={{ fontSize: 12 }}>{row.how}</div>
            </span>
            <span className={`tag ${row.now === "REAL" ? "real" : row.now === "RULE_BASED" ? "rule" : row.now === "DISABLED" ? "off" : "sim"}`}>{row.now}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
