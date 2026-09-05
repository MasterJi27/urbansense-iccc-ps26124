import { Link } from "react-router-dom";
import { useUi } from "../i18n.jsx";

export default function CctvBoothCard() {
  const { t } = useUi();
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const joinUrl = `${origin}/cctv`;
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=148x148&data=${encodeURIComponent(joinUrl)}`;
  return (
    <div className="card field-booth-card" style={{ marginBottom: 12 }}>
      <div className="field-booth-grid">
        <div>
          <h4 style={{ margin: "0 0 6px" }}>{t("cctvBoothTitle")}</h4>
          <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>{t("cctvBoothSub")}</p>
          <div className="stat-row"><span className="muted">Lens</span><b>This browser / USB / cheap Wi-Fi cam</b></div>
          <div className="stat-row"><span className="muted">DVR file</span><b>HP · CP Plus · XM · any export JPEG</b></div>
          <div className="stat-row"><span className="muted">Snapshot URL</span><b>ONVIF / CGI still — not RTSP video</b></div>
          <div className="stat-row"><span className="muted">Depot PC</span><b className="mono">scripts/cctv-bridge.ps1</b></div>
          <div className="field-row" style={{ marginTop: 12 }}>
            <Link className="btn" to="/cctv">{t("cctvOpen")}</Link>
          </div>
        </div>
        <div className="field-qr-wrap">
          <img src={qrSrc} width={148} height={148} alt="QR to CCTV bridge" />
          <span className="muted mono" style={{ fontSize: 11, wordBreak: "break-all" }}>{joinUrl}</span>
        </div>
      </div>
    </div>
  );
}
