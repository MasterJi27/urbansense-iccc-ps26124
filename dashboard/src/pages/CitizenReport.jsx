import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useUi } from "../i18n.jsx";

const CLAIM_KEY = "urbansense_citizen_claim";

export default function CitizenReport() {
  const { t, lang, toggleLang } = useUi();
  const [lat, setLat] = useState(28.6328);
  const [lng, setLng] = useState(77.2195);
  const [acc, setAcc] = useState(null);
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [last, setLast] = useState(null);
  const [tickets, setTickets] = useState([]);

  useEffect(() => {
    if (!navigator.geolocation) return undefined;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude);
        setLng(pos.coords.longitude);
        setAcc(pos.coords.accuracy);
      },
      () => {},
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, []);

  useEffect(() => {
    const claim = localStorage.getItem(CLAIM_KEY);
    if (!claim) return undefined;
    api(`/citizen/tickets?claim=${encodeURIComponent(claim)}`)
      .then((data) => setTickets(data.items || []))
      .catch(() => {});
  }, [last]);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const prior = localStorage.getItem(CLAIM_KEY) || undefined;
      const data = await api("/citizen/report", {
        method: "POST",
        body: JSON.stringify({
          latitude: Number(lat),
          longitude: Number(lng),
          gps_accuracy: acc,
          description: description.trim() || undefined,
          contact: contact.trim() || undefined,
          claim_token: prior,
        }),
      });
      if (data.claim_token) localStorage.setItem(CLAIM_KEY, data.claim_token);
      setLast(data);
      setDescription("");
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="field-shell citizen-shell">
      <header className="field-head">
        <div>
          <div className="folio-brand">URBANSENSE</div>
          <div className="folio-brand-sub">{t("citizenTitle")}</div>
        </div>
        <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>{t("lang")}</button>
      </header>
      <p className="muted" style={{ padding: "0 16px", maxWidth: 520 }}>{t("citizenSub")}</p>
      <form className="field-join" onSubmit={submit}>
        <label htmlFor="c-desc">What did you see?</label>
        <textarea id="c-desc" rows={3} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Joint noise / visible crack / standing water near pier…" />
        <label htmlFor="c-contact">Phone (optional, masked at ICCC)</label>
        <input id="c-contact" value={contact} onChange={(e) => setContact(e.target.value)} maxLength={64} inputMode="tel" />
        <p className="muted" style={{ fontSize: 13 }}>GPS {Number(lat).toFixed(5)}, {Number(lng).toFixed(5)}{acc ? ` · ${Math.round(acc)} m` : ""}</p>
        {err && <div role="alert" className="err">{err}</div>}
        <button className="btn folio-stamp" type="submit" disabled={busy}>{busy ? "…" : t("citizenSend")}</button>
      </form>
      {last && (
        <div className="field-result" style={{ margin: "0 16px 16px" }}>
          <div className="field-result-top">
            <span className="tag rule">RULE_BASED</span>
            <b className="mono">{last.event_code}</b>
          </div>
          <p>{last.department?.department_desk}. You keep a claim token in this browser — not a shared inbox.</p>
        </div>
      )}
      <section style={{ padding: "0 16px 24px" }}>
        <h2 style={{ fontSize: 16 }}>{t("citizenMine")}</h2>
        {tickets.length === 0 ? <p className="muted">No tickets on this phone yet.</p> : (
          <ul className="citizen-list">
            {tickets.map((row) => (
              <li key={row.id}>
                <b className="mono">{row.public_code}</b>
                <span>{row.event_type} · {row.status}</span>
                <span className="muted">{row.extra?.department_desk}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="muted" style={{ fontSize: 12 }}><Link to="/login">ICCC officers sign in here</Link> · ASSISTS AUTHORITIES — DOES NOT ACCUSE</p>
      </section>
    </div>
  );
}
