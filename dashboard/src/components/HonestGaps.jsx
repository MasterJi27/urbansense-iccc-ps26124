import { useEffect, useState } from "react";
import { api } from "../api";
import { useUi } from "../i18n.jsx";

const GAPS = [
  { req: "iPhone / Android camera", now: "REAL", how: "Phone only: Chrome or Safari /field. ICCC desk is a different login. No CCTV page." },
  { req: "Windshield boxes", now: "RULE_BASED", how: "On-device 640 India RDD. Road-band + full-frame merge. IoU tracker is persistence, same weights. Overlay is WASM; WebGPU only if the ONNX Runtime GPU EP attaches. Official event is the Azure still. Not a new test mAP." },
  { req: "Cloud road-damage on stills", now: "REAL", how: "Azure App Service YOLOv8s 640 ONNX CPU. More cores help stills. Not a GPU stream. Cabin bay still cannot invent a road defect." },
  { req: "ICCC live desk", now: "REAL", how: "Phone pushes overlay ticks on /ws/field-live. Desk listens on /ws/live. Round-trip is tens of ms, not 1 ms." },
  { req: "Flutter windshield", now: "REAL", how: "Same /field page in a WebView. Not a second detector." },
  { req: "Pedestrian count this frame", now: "REAL", how: "COCO person on this still/overlay. Not a child detector, not a day-long street census." },
  { req: "Shake / rash from phone IMU", now: "RULE_BASED", how: "Accelerometer spike. Fast + shake → RASH_DRIVING. Slow + shake → pothole hit." },
  { req: "Fleet confirm (USP)", now: "RULE_BASED", how: "Second independent bus in 40 m / 6 h confirms. One phone cannot close a city ticket." },
  { req: "Indian MoRTH sign model", now: "DISABLED", how: "GIS missing-sign geofence only. Not shipped as a classifier." },
  { req: "School-child classifier", now: "RULE_BASED", how: "School geofence + speed drop. No child detector." },
];

export default function HonestGaps() {
  const { t } = useUi();
  const [maps, setMaps] = useState(null);
  const [composio, setComposio] = useState(null);
  useEffect(() => {
    api("/maps/config").then(setMaps).catch(() => setMaps({ enabled: false }));
    api("/ai/capabilities").then((c) => setComposio(c.composio || null)).catch(() => setComposio(null));
  }, []);
  const rows = [
    ...GAPS,
    {
      req: "Officer ping (Composio)",
      now: composio?.honesty || "DISABLED",
      how: composio?.note || "COMPOSIO_API_KEY not set. Fleet confirm still saves.",
    },
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
