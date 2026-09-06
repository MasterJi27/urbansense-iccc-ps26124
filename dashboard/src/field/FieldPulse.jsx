import { useUi } from "../i18n.jsx";

function pathFrom(values, w, h, minY, maxY) {
  if (!values.length) return "";
  const span = Math.max(1e-6, maxY - minY);
  return values
    .map((v, i) => {
      const x = values.length === 1 ? 0 : (i / (values.length - 1)) * w;
      const y = h - ((v - minY) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

const CLASSES = [
  { id: "D40", label: "Pothole", color: "#c45c26" },
  { id: "D20", label: "Alligator", color: "#8a6d12" },
  { id: "D00", label: "Long crack", color: "#3d5a40" },
  { id: "D10", label: "Cross crack", color: "#4a6670" },
];

export default function FieldPulse({ imuSeries, detSeries, classCounts, overlayMs, azureMs, burstLeftMs }) {
  const { t } = useUi();
  const imu = imuSeries || [];
  const dets = detSeries || [];
  const imuVals = imu.map((p) => p.mag);
  const detVals = dets.map((p) => p.count);
  const imuMax = Math.max(12, ...imuVals, 1);
  const detMax = Math.max(3, ...detVals, 1);
  const counts = classCounts || {};
  const maxBar = Math.max(1, ...CLASSES.map((c) => counts[c.id] || 0));

  return (
    <section className="field-pulse" aria-label="Patrol pulse">
      <header className="field-pulse-head">
        <b>{t("fieldPulseTitle")}</b>
        <span className="muted">
          {t("fieldPulseHint")} {overlayMs > 0 ? `${overlayMs} ms` : "—"}. {t("fieldAzureMs")} {azureMs > 0 ? `${azureMs} ms` : t("fieldAzureAfter")}.
        </span>
      </header>
      {burstLeftMs > 0 ? (
        <p className="field-burst">{t("fieldBurstLeft")} {Math.ceil(burstLeftMs / 1000)}s</p>
      ) : null}
      <div className="field-pulse-grid">
        <div className="field-pulse-card">
          <span className="field-pulse-kicker">{t("fieldImuLine")}</span>
          <svg viewBox="0 0 240 72" className="field-pulse-svg" aria-hidden="true">
            <path d={pathFrom(imuVals, 240, 72, 0, imuMax)} fill="none" stroke="#c45c26" strokeWidth="2" />
          </svg>
        </div>
        <div className="field-pulse-card">
          <span className="field-pulse-kicker">{t("fieldDetLine")}</span>
          <svg viewBox="0 0 240 72" className="field-pulse-svg" aria-hidden="true">
            <path d={pathFrom(detVals, 240, 72, 0, detMax)} fill="none" stroke="#3d5a40" strokeWidth="2" />
          </svg>
        </div>
      </div>
      <div className="field-bars" role="img" aria-label="Class counts this patrol">
        {CLASSES.map((c) => {
          const n = counts[c.id] || 0;
          const pct = Math.round((n / maxBar) * 100);
          return (
            <div key={c.id} className="field-bar-row">
              <span>{c.label}</span>
              <span className="field-bar-track">
                <span className="field-bar-fill" style={{ width: `${pct}%`, background: c.color }} />
              </span>
              <b className="mono">{n}</b>
            </div>
          );
        })}
      </div>
    </section>
  );
}
