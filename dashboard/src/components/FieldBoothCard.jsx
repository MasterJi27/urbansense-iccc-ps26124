import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useUi } from "../i18n.jsx";
import { useToast } from "./Toast.jsx";

export default function FieldBoothCard() {
  const { t } = useUi();
  const toast = useToast();
  const [booth, setBooth] = useState(null);
  const [busy, setBusy] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const joinUrl = useMemo(() => {
    const base = `${origin}/field`;
    return booth?.code ? `${base}?code=${booth.code}` : base;
  }, [origin, booth?.code]);
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=168x168&data=${encodeURIComponent(joinUrl)}`;

  useEffect(() => {
    api("/auth/field-booth").then(setBooth).catch(() => setBooth(null));
  }, []);

  async function arm() {
    setBusy(true);
    try {
      const next = await api("/auth/field-booth", { method: "POST", body: "{}" });
      setBooth(next);
      toast.success(t("fieldArmed"));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(joinUrl);
      toast.success(t("fieldCopied"));
    } catch {
      toast.error(joinUrl);
    }
  }

  return (
    <div className="card field-booth-card" style={{ marginBottom: 12 }}>
      <div className="field-booth-grid">
        <div>
          <h4 style={{ margin: "0 0 6px" }}>{t("fieldBoothTitle")}</h4>
          <p className="muted" style={{ fontSize: 15, margin: "0 0 10px" }}>{t("fieldBoothSub")}</p>
          <ol className="booth-how">
            <li>{t("boothHow1")}</li>
            <li>{t("boothHow2")}</li>
            <li>{t("boothHow3")}</li>
            <li>{t("boothHow4")}</li>
          </ol>
          <p className="muted" style={{ fontSize: 14, margin: "0 0 10px" }}>{t("fieldFourPhones")}</p>
          <div className="field-row" style={{ marginTop: 12 }}>
            <button className="btn" type="button" disabled={busy} onClick={arm}>{busy ? "…" : t("fieldArm")}</button>
            <button className="btn ghost" type="button" onClick={copyLink}>{t("fieldCopy")}</button>
          </div>
          {booth?.code && (
            <p className="mono" style={{ fontSize: 28, letterSpacing: "0.28em", margin: "14px 0 0" }}>{booth.code}</p>
          )}
          <p className="muted" style={{ fontSize: 13, margin: "8px 0 0", wordBreak: "break-all" }}>{joinUrl}</p>
        </div>
        <div className="field-qr-wrap">
          <img src={qrSrc} width={168} height={168} alt={t("fieldQrAlt")} />
          <span className="muted" style={{ fontSize: 12 }}>{t("fieldQrHint")}</span>
        </div>
      </div>
    </div>
  );
}
