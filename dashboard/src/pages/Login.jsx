import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, setSession } from "../api";
import { useUi } from "../i18n.jsx";

function safeNext(raw) {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("://")) return "/";
  return raw;
}

export default function Login() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const { t, lang, toggleLang } = useUi();
  const [email, setEmail] = useState("admin@urbansense.local");
  const [password, setPassword] = useState("UrbanSense@2026");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const data = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setSession(data);
      nav(safeNext(params.get("next")));
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="login-split login-register">
      <section className="login-brand" aria-label="SadakSaarthi">
        <div>
          <div className="folio-brand">SADAKSAARTHI</div>
          <div className="folio-brand-sub">ICCC COMMAND REGISTER</div>
          <h1>The ICCC officer&apos;s endorsement register</h1>
          <p>Delhi fleet command. Honest AI labels. Phone-edge, not a Western ITS demo. No video upload. No collapse prediction.</p>
          <div className="login-stats">
            <div className="login-stat"><b>~1KB</b><span>per observation</span></div>
            <div className="login-stat"><b>40m/6h</b><span>fusion window</span></div>
            <div className="login-stat"><b>DPDP</b><span>plate masked</span></div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
            <span className="tag real">REAL</span>
            <span className="tag rule">RULE_BASED</span>
            <span className="tag sim">SEED / SIMULATED</span>
          </div>
        </div>
        <p style={{ margin: 0, fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" }}>Demonstration data — not a live deployment.</p>
      </section>
      <div className="login-form-wrap">
        <form className="login" onSubmit={submit}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ margin: 0, letterSpacing: "0.12em" }}>ICCC SIGN-IN</h2>
            <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>
              {t("lang")}
            </button>
          </div>
          <label htmlFor="login-email">{t("email")}</label>
          <input id="login-email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
          <label htmlFor="login-pass">{t("password")}</label>
          <input id="login-pass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          {err && <div role="alert" className="err" style={{ marginTop: 10 }}>{err}</div>}
          <button className="btn folio-stamp" type="submit" disabled={loading}>
            <span style={{ display: "block", lineHeight: 1.15 }}>ENTER ICCC</span>
            <span style={{ display: "block", fontFamily: "Noto Sans Devanagari, sans-serif", fontSize: 13, fontWeight: 700, letterSpacing: 0, textTransform: "none" }}>आईसीसीसी में प्रवेश</span>
          </button>
          <p className="muted" style={{ fontSize: 12, marginTop: 16, letterSpacing: "0.04em" }}>
            admin / inspector / operator / superadmin @urbansense.local
          </p>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            <Link to="/report">Citizen bridge report</Link> — own tickets only, no ICCC password.
          </p>
        </form>
      </div>
    </div>
  );
}
