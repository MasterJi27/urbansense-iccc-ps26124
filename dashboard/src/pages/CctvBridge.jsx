import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, getToken, setSession } from "../api";
import { useUi } from "../i18n.jsx";

async function blobFromVideo(video) {
  if (!video || !video.videoWidth) throw new Error("Lens not ready");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("JPEG encode failed"))), "image/jpeg", 0.82);
  });
}

function demoStillBlob(vendor, code) {
  const canvas = document.createElement("canvas");
  canvas.width = 960;
  canvas.height = 540;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#1a1c16";
  ctx.fillRect(0, 0, 960, 540);
  ctx.strokeStyle = "#b0342b";
  ctx.lineWidth = 4;
  ctx.strokeRect(16, 16, 928, 508);
  ctx.fillStyle = "#edf2e8";
  ctx.font = "700 42px Saira Extra Condensed, sans-serif";
  ctx.fillText("URBANSENSE CCTV BRIDGE", 40, 90);
  ctx.font = "600 28px Saira Condensed, sans-serif";
  ctx.fillText(`${vendor} · ${code}`, 40, 150);
  ctx.font = "16px Roboto Mono, monospace";
  ctx.fillStyle = "#c4c2ba";
  ctx.fillText("DEMO STILL — not a live DVR decode", 40, 200);
  ctx.fillText("One JPEG. No RTSP. No our hardware.", 40, 230);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
}

export default function CctvBridge() {
  const { t, lang, toggleLang } = useUi();
  const [params] = useSearchParams();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const [authed, setAuthed] = useState(!!getToken());
  const [pin, setPin] = useState(params.get("code") || "");
  const [joinErr, setJoinErr] = useState("");
  const [presets, setPresets] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [vendor, setVendor] = useState("BROWSER");
  const [mode, setMode] = useState("LENS");
  const [code, setCode] = useState(params.get("cam") || "CAM-DVR-01");
  const [busId, setBusId] = useState(params.get("bus") || "BUS-042");
  const [bay, setBay] = useState("FRONT");
  const [kind, setKind] = useState("BUS_CCTV");
  const [snapUrl, setSnapUrl] = useState("");
  const [camErr, setCamErr] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);
  const preset = presets.find((p) => p.id === vendor) || presets[0];

  useEffect(() => {
    if (!authed) return undefined;
    api("/cameras/presets").then((b) => setPresets(b.items || [])).catch(() => setPresets([]));
    api("/cameras").then(setCameras).catch(() => setCameras([]));
    return undefined;
  }, [authed]);

  useEffect(() => {
    const row = presets.find((p) => p.id === vendor);
    if (row?.url_hint && row.protocol === "HTTP_SNAPSHOT") {
      setSnapUrl(row.url_hint);
    }
  }, [vendor, presets]);

  useEffect(() => {
    if (!authed || mode !== "LENS") return undefined;
    let dead = false;
    (async () => {
      setCamErr("");
      try {
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((tr) => tr.stop());
          streamRef.current = null;
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        });
        if (dead) {
          stream.getTracks().forEach((tr) => tr.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
      } catch (ex) {
        if (!dead) setCamErr(ex.message || "Lens denied. Use FILE export or DEMO still.");
      }
    })();
    return () => {
      dead = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((tr) => tr.stop());
        streamRef.current = null;
      }
    };
  }, [authed, mode]);

  async function join(e) {
    e.preventDefault();
    setJoinErr("");
    try {
      const data = await api("/auth/field-join", { method: "POST", body: JSON.stringify({ code: pin.trim() }) });
      setSession(data);
      setAuthed(true);
    } catch (ex) {
      setJoinErr(ex.message);
    }
  }

  async function registerCam() {
    await api("/cameras", {
      method: "POST",
      body: JSON.stringify({ code, vendor, bay, bus_code: busId, kind, label: `${vendor}_${bay}` }),
    });
    setCameras(await api("/cameras"));
  }

  async function postStill(blob, extra = {}) {
    setErr("");
    setResult(null);
    setBusy("still");
    try {
      await registerCam().catch(() => {});
      const fd = new FormData();
      fd.append("file", blob, `${code}.jpg`);
      fd.append("latitude", "28.6328");
      fd.append("longitude", "77.2195");
      fd.append("source_id", code);
      fd.append("bus_id", busId);
      fd.append("camera_bay", bay);
      fd.append("vendor", vendor);
      fd.append("source_kind", kind);
      const ingested = await api("/ingest/cctv/still", { method: "POST", body: fd });
      const ev = ingested.event || {};
      setResult({
        path: extra.path || ev.extra?.ai_status || "RULE_BASED",
        title: ev.public_code,
        type: ev.event_type,
        created: ingested.created_event,
        patrol: ev.extra?.patrol_state,
        eventId: ev.id,
        note: extra.note || "One JPEG ingested. Not a live NVR stream.",
      });
      setCameras(await api("/cameras").catch(() => cameras));
    } catch (ex) {
      setErr(ex.message);
      if (!getToken()) setAuthed(false);
    } finally {
      setBusy("");
    }
  }

  async function senseLens() {
    const blob = await blobFromVideo(videoRef.current);
    await postStill(blob, { path: "REAL", note: "Browser / USB / phone lens. Same still pipeline as every DVR." });
  }

  async function senseFile(file) {
    if (!file) return;
    await postStill(file, { path: "RULE_BASED", note: "JPEG exported from vendor DVR software. We never talk that vendor protocol." });
  }

  async function senseDemo() {
    const blob = await demoStillBlob(vendor, code);
    await postStill(blob, { path: "SIMULATED", note: "Jury demo still. Swap this for a real DVR export or lens when hardware is on the table." });
  }

  async function sensePull() {
    setErr("");
    setResult(null);
    setBusy("pull");
    try {
      await registerCam().catch(() => {});
      const ingested = await api("/cameras/pull", {
        method: "POST",
        body: JSON.stringify({
          snapshot_url: snapUrl,
          code,
          vendor,
          bay,
          bus_code: busId,
          kind,
        }),
      });
      const ev = ingested.event || {};
      setResult({
        path: "RULE_BASED",
        title: ev.public_code,
        type: ev.event_type,
        created: ingested.created_event,
        eventId: ev.id,
        note: "HTTP snapshot pulled. Password is not stored. RTSP is not decoded.",
      });
    } catch (ex) {
      setErr(ex.message);
      if (!getToken()) setAuthed(false);
    } finally {
      setBusy("");
    }
  }

  if (!authed) {
    return (
      <div className="field-shell">
        <header className="field-head">
          <div>
            <div className="folio-brand">URBANSENSE</div>
            <div className="folio-brand-sub">{t("cctvUnit")}</div>
          </div>
          <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>{t("lang")}</button>
        </header>
        <form className="field-join" onSubmit={join}>
          <h1>{t("cctvJoinTitle")}</h1>
          <p className="muted">{t("cctvJoinSub")}</p>
          <label htmlFor="cctv-pin">{t("fieldPin")}</label>
          <input id="cctv-pin" className="field-pin" inputMode="numeric" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          {joinErr && <div role="alert" className="err">{joinErr}</div>}
          <button className="btn folio-stamp" type="submit" disabled={pin.length < 6}>{t("fieldPing")}</button>
          <Link className="muted" to="/login?next=/cctv">{t("fieldIcccLogin")}</Link>
        </form>
      </div>
    );
  }

  return (
    <div className="field-shell">
      <header className="field-head">
        <div>
          <div className="folio-brand">URBANSENSE</div>
          <div className="folio-brand-sub">{t("cctvUnit")}</div>
        </div>
        <div className="field-head-actions">
          <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>{t("lang")}</button>
          <Link className="field-link" to="/">{t("fieldBackIccc")}</Link>
        </div>
      </header>

      <p className="muted" style={{ fontSize: 13 }}>{t("cctvHonest")}</p>

      <div className="field-row">
        {["LENS", "FILE", "HTTP", "DEMO"].map((m) => (
          <button key={m} className={`chip ${mode === m ? "active" : ""}`} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}>{t(`cctvMode${m}`)}</button>
        ))}
      </div>

      <label className="field-bus">
        <span>{t("cctvVendor")}</span>
        <select value={vendor} onChange={(e) => setVendor(e.target.value)}>
          {(presets.length ? presets : [{ id: "BROWSER", label: "Browser lens" }]).map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
      </label>
      {preset && <p className="muted" style={{ fontSize: 12, margin: 0 }}>{preset.how} <span className={`tag ${preset.honesty === "REAL" ? "real" : preset.honesty === "DISABLED" ? "off" : "rule"}`}>{preset.honesty}</span></p>}

      <div className="field-row">
        <label className="field-bus" style={{ flex: 1 }}>
          <span>{t("cctvCode")}</span>
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
        </label>
        <label className="field-bus" style={{ flex: 1 }}>
          <span>{t("fieldBus")}</span>
          <input value={busId} onChange={(e) => setBusId(e.target.value.toUpperCase())} />
        </label>
      </div>
      <div className="field-row">
        {["FRONT", "REAR", "LEFT", "RIGHT", "CABIN"].map((b) => (
          <button key={b} className={`chip ${bay === b ? "active" : ""}`} type="button" onClick={() => setBay(b)}>{b}</button>
        ))}
        <button className={`chip ${kind === "ROAD_CCTV" ? "active" : ""}`} type="button" onClick={() => setKind((k) => (k === "ROAD_CCTV" ? "BUS_CCTV" : "ROAD_CCTV"))}>
          {kind === "ROAD_CCTV" ? t("cctvRoad") : t("cctvBus")}
        </button>
      </div>

      {mode === "LENS" && (
        <div className="field-stage">
          <video ref={videoRef} className="field-video" playsInline muted autoPlay />
          {camErr && <div className="field-cam-fallback"><p>{camErr}</p></div>}
        </div>
      )}

      {mode === "FILE" && (
        <div className="card-pad-sm" style={{ border: "1px solid var(--line)", padding: 12 }}>
          <p className="muted" style={{ fontSize: 13 }}>{t("cctvFileHint")}</p>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/*" onChange={(e) => senseFile(e.target.files?.[0])} />
        </div>
      )}

      {mode === "HTTP" && (
        <label className="field-bus">
          <span>{t("cctvSnapUrl")}</span>
          <input value={snapUrl} onChange={(e) => setSnapUrl(e.target.value)} placeholder={preset?.url_hint || "http://192.168.1.64/snapshot.jpg"} />
          <span className="muted" style={{ fontSize: 11, textTransform: "none", letterSpacing: 0 }}>{t("cctvSnapHint")}</span>
        </label>
      )}

      {mode === "DEMO" && <p className="muted" style={{ fontSize: 13 }}>{t("cctvDemoHint")}</p>}

      <div className="field-row">
        {mode === "LENS" && <button className="btn folio-stamp field-sense" type="button" disabled={!!busy} onClick={senseLens}>{busy ? "…" : t("cctvSense")}</button>}
        {mode === "HTTP" && <button className="btn folio-stamp field-sense" type="button" disabled={!!busy || !snapUrl} onClick={sensePull}>{busy ? "…" : t("cctvPull")}</button>}
        {mode === "DEMO" && <button className="btn folio-stamp field-sense" type="button" disabled={!!busy} onClick={senseDemo}>{busy ? "…" : t("cctvDemo")}</button>}
      </div>

      {err && <div role="alert" className="err">{err}</div>}
      {result && (
        <div className="field-result">
          <div className="field-result-top">
            <span className={`tag ${result.path === "REAL" ? "real" : result.path === "SIMULATED" ? "sim" : "rule"}`}>{result.path}</span>
            <b className="mono">{result.title}</b>
            {result.created ? <span className="tag info">FIRST_SIGHTING</span> : null}
          </div>
          <p>{result.type}{result.patrol ? ` · ${result.patrol}` : ""}</p>
          <p className="muted">{result.note}</p>
          {result.eventId && <Link to={`/events/${result.eventId}`}>{t("fieldOpenEvent")}</Link>}
        </div>
      )}

      {cameras.length > 0 && (
        <div>
          <h4 style={{ margin: "12px 0 6px" }}>{t("cctvBound")}</h4>
          {cameras.slice(0, 8).map((c) => (
            <div key={c.id} className="stat-row">
              <span className="mono">{c.code}</span>
              <span className="muted">{c.device_label} · {c.bus_code || "ROAD"}</span>
            </div>
          ))}
        </div>
      )}
      <p className="muted field-honest">{t("cctvScript")}</p>
    </div>
  );
}
