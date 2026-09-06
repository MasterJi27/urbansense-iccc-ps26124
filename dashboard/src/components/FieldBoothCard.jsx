import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useUi } from "../i18n.jsx";
import { useToast } from "./Toast.jsx";

function busParam(code) {
  const digits = String(code || "").replace(/\D/g, "");
  return digits || String(code || "").toUpperCase();
}

function joinsCount(booth) {
  if (!booth) return 0;
  if (Array.isArray(booth.joins)) return booth.joins.length;
  if (typeof booth.joins === "number") return booth.joins;
  return 0;
}

export default function FieldBoothCard() {
  const { t } = useUi();
  const toast = useToast();
  const [booth, setBooth] = useState(null);
  const [buses, setBuses] = useState([]);
  const [busCode, setBusCode] = useState("");
  const [busy, setBusy] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const boundBus = booth?.bus_code || busCode;
  const joinUrl = useMemo(() => {
    const base = `${origin}/field`;
    if (!booth?.code) return base;
    const q = new URLSearchParams({ code: String(booth.code) });
    if (boundBus) q.set("bus", busParam(boundBus));
    return `${base}?${q.toString()}`;
  }, [origin, booth?.code, boundBus]);
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=168x168&data=${encodeURIComponent(joinUrl)}`;

  useEffect(() => {
    api("/buses").then((rows) => {
      const list = Array.isArray(rows) ? rows : [];
      setBuses(list);
    }).catch(() => setBuses([]));
    api("/auth/field-booth").then((next) => {
      setBooth(next);
      if (next?.bus_code) setBusCode(next.bus_code);
    }).catch(() => setBooth(null));
  }, []);

  async function arm() {
    if (!busCode) {
      toast.error(t("fieldPickBus"));
      return;
    }
    setBusy(true);
    try {
      const next = await api("/auth/field-booth", {
        method: "POST",
        body: JSON.stringify({ bus_code: busCode }),
      });
      setBooth(next);
      if (next?.bus_code) setBusCode(next.bus_code);
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

  const joined = joinsCount(booth);

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
          <label htmlFor="booth-bus-select" style={{ display: "grid", gap: 4, fontSize: 13, fontWeight: 700 }}>
            {t("fieldPickBus")}
            <select
              id="booth-bus-select"
              className="field-num"
              style={{ fontSize: 18, letterSpacing: "0.04em", textAlign: "left" }}
              value={busCode}
              onChange={(e) => setBusCode(e.target.value)}
              required
            >
              <option value="">{t("fieldPickBus")}</option>
              {boundBus && !buses.some((b) => b.code === boundBus) ? (
                <option value={boundBus}>{boundBus}</option>
              ) : null}
              {buses.map((b) => (
                <option key={b.id || b.code} value={b.code}>{b.code}{b.registration ? ` · ${b.registration}` : ""}</option>
              ))}
            </select>
          </label>
          {buses.length === 0 && (
            <input
              className="field-num"
              style={{ marginTop: 8, fontSize: 16 }}
              placeholder="BUS-017"
              value={busCode}
              onChange={(e) => setBusCode(e.target.value.toUpperCase())}
              aria-label={t("fieldPickBus")}
            />
          )}
          <div className="field-row" style={{ marginTop: 12 }}>
            <button className="btn" type="button" disabled={busy || !busCode} onClick={arm}>{busy ? "…" : t("fieldArm")}</button>
            <button className="btn ghost" type="button" onClick={copyLink}>{t("fieldCopy")}</button>
          </div>
          {booth?.code && (
            <p className="mono" style={{ fontSize: 28, letterSpacing: "0.28em", margin: "14px 0 0" }}>{booth.code}</p>
          )}
          {boundBus && booth?.code && (
            <p style={{ margin: "8px 0 0", fontSize: 15 }}>
              {t("fieldBoundBus")} <b className="mono">{boundBus}</b>
              {joined ? <span className="muted"> · {joined} joined</span> : null}
            </p>
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
