import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import DetectionOverlay from "../components/DetectionOverlay.jsx";
import { useFieldOverlay } from "../field/useFieldOverlay.js";
import { api, getToken, setSession } from "../api";
import { useUi } from "../i18n.jsx";

function asBusFromCctv(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  if (digits) return `BUS-${digits.padStart(3, "0")}`;
  const up = String(raw || "").toUpperCase();
  return up.startsWith("BUS-") ? up : "BUS-017";
}

const CCTV_BAYS = ["FRONT", "REAR", "LEFT", "RIGHT"];

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
  const [busNum, setBusNum] = useState(() => {
    const raw = params.get("bus") || "17";
    return String(raw).replace(/\D/g, "") || "17";
  });
  const [slot, setSlot] = useState(() => {
    const n = Number(params.get("phone") || 1);
    return n >= 1 && n <= 4 ? n : 1;
  });
  const busId = asBusFromCctv(busNum);
  const bay = CCTV_BAYS[slot - 1];
  const code = `${busId}-P${slot}`;
  const kind = "BUS_CCTV";
  const [snapUrl, setSnapUrl] = useState("");
  const [camErr, setCamErr] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);
  const [boxes, setBoxes] = useState([]);
  const [patrol, setPatrol] = useState(true);

  async function blobFromVideo() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) throw new Error("Lens not ready");
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("JPEG encode failed"))), "image/jpeg", 0.82);
    });
  }

  async function ingestStill(blob) {
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
    return api("/ingest/cctv/still", { method: "POST", body: fd });
  }

  const overlay = useFieldOverlay({
    authed: authed && mode === "LENS",
    patrol,
    videoRef,
    blobFromVideo,
    postStill: ingestStill,
    setBoxes,
    setResult,
  });

  useEffect(() => {
    if (!authed) return undefined;
    api("/cameras/presets").then((b) => setPresets(b.items || [])).catch(() => setPresets([]));
    api("/cameras").then(setCameras).catch(() => setCameras([]));
    return undefined;
  }, [authed]);

  useEffect(() => {
    if (!authed) return undefined;
    const beat = () => {
      api("/sensor-nodes/heartbeat", {
        method: "POST",
        body: JSON.stringify({
          sensor_code: code,
          bus_code: busId,
          camera_status: streamRef.current ? "ONLINE" : "DEGRADED",
          gps_status: "UNKNOWN",
          imu_status: "UNKNOWN",
          network_type: "CELL",
          ai_mode: patrol ? "AUTO" : "MANUAL",
          latitude: 28.6328,
          longitude: 77.2195,
          last_boxes: [...(overlay.lastBoxes.current || []), ...(overlay.lastPeople.current || [])],
          person_count: (overlay.lastPeople.current || []).length,
          overlay_fps: overlay.fpsRef?.current || 0,
          overlay_mode: overlay.mode,
        }),
      }).catch(() => {});
    };
    beat();
    const id = window.setInterval(beat, 3000);
    return () => window.clearInterval(id);
  }, [authed, busId, code, patrol, overlay.mode]);

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
        if (!dead) setCamErr(ex.message || "Camera closed. Use a photo from the gallery.");
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
      const ingested = await ingestStill(blob);
      const ev = ingested.event || {};
      const found = ingested.detections || ev.extra?.detections || [];
      setBoxes(found);
      setResult({
        path: extra.path || ev.extra?.ai_status || "RULE_BASED",
        title: ev.public_code,
        type: ev.event_type,
        created: ingested.created_event,
        patrol: ev.extra?.patrol_state,
        eventId: ev.id,
        note: found.length
          ? `${found.length} box(es) on this photo.`
          : (extra.note || "Photo sent. No box on this frame."),
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
    const blob = await blobFromVideo();
    await postStill(blob, { path: "REAL", note: "This phone / tablet camera." });
  }

  async function senseFile(file) {
    if (!file) return;
    await postStill(file, { path: "RULE_BASED", note: "Photo from the Wi-Fi camera app." });
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
        note: "HTTP snapshot pulled. Password is not stored. RTSP is not decoded. Live boxes on this page are the browser lens, not the DVR JPEG.",
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
          <p className="how-kicker">{t("howTitle")}</p>
          <ol className="how-simple">
            <li>{t("how1")}</li>
            <li>{t("how2")}</li>
            <li>{t("how3")}</li>
            <li>{t("how4")}</li>
          </ol>
          <label htmlFor="cctv-pin">{t("fieldPin")}</label>
          <input id="cctv-pin" className="field-pin" inputMode="numeric" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          <label htmlFor="cctv-bus">{t("fieldBusNum")}</label>
          <input
            id="cctv-bus"
            className="field-num"
            inputMode="numeric"
            value={busNum}
            onChange={(e) => setBusNum(e.target.value.replace(/\D/g, "").slice(0, 3))}
            placeholder="17"
          />
          <p className="muted" style={{ fontSize: 15, margin: 0 }}>{t("fieldPhoneWhich")}</p>
          <div className="phone-slots">
            {[1, 2, 3, 4].map((n) => (
              <button key={n} className={`chip ${slot === n ? "active" : ""}`} type="button" aria-pressed={slot === n} onClick={() => setSlot(n)}>
                {t("fieldPhoneN")} {n}
              </button>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 14, margin: 0 }}>{t("fieldFourPhones")}</p>
          {joinErr && <div role="alert" className="err">{joinErr}</div>}
          <button className="btn folio-stamp" type="submit" disabled={pin.length < 6 || !busNum}>{t("fieldPing")}</button>
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

      <div className="field-status" role="status">
        <span className="tag real">{busId}</span>
        <span className="tag info">{t("fieldPhoneN")} {slot}</span>
        <span className={`tag ${patrol ? "real" : "rule"}`}>{patrol ? t("fieldAuto") : t("fieldManual")}</span>
        {mode === "LENS" && (
          <span className={`tag ${overlay.mode === "ondevice" ? "real" : overlay.mode === "cloud" ? "rule" : "off"}`}>
            {overlay.mode === "ondevice" ? t("fieldOnDevice") : overlay.mode === "cloud" ? t("fieldCloudPreview") : t("fieldWait")}
          </span>
        )}
        {mode === "LENS" && <span className="tag info">{t("fieldPeople")} {overlay.personCount}</span>}
      </div>

      <p className="muted" style={{ fontSize: 15 }}>{t("cctvWifiWhy")}</p>

      <div className="easy-pick">
        <button className={`chip ${mode === "LENS" ? "active" : ""}`} type="button" onClick={() => { setMode("LENS"); setVendor("BROWSER"); }}>
          {t("cctvEasyPhone")}
        </button>
        <button className={`chip ${mode === "FILE" ? "active" : ""}`} type="button" onClick={() => setMode("FILE")}>
          {t("cctvEasyPhoto")}
        </button>
      </div>

      <label className="field-bus">
        <span>{t("fieldBusNum")}</span>
        <input className="field-num" value={busNum} onChange={(e) => setBusNum(e.target.value.replace(/\D/g, "").slice(0, 3))} inputMode="numeric" />
      </label>
      <p className="muted" style={{ fontSize: 15 }}>{t("fieldPhoneWhich")}</p>
      <div className="phone-slots">
        {[1, 2, 3, 4].map((n) => (
          <button key={n} className={`chip ${slot === n ? "active" : ""}`} type="button" aria-pressed={slot === n} onClick={() => setSlot(n)}>
            {t("fieldPhoneN")} {n}
          </button>
        ))}
      </div>

      {mode === "LENS" && (
        <div className="field-stage">
          <video ref={videoRef} className="field-video" playsInline muted autoPlay />
          <DetectionOverlay boxes={boxes} />
          {camErr && <div className="field-cam-fallback"><p>{camErr}</p></div>}
        </div>
      )}

      {mode === "FILE" && (
        <div className="card-pad-sm" style={{ border: "1px solid var(--line)", padding: 12 }}>
          <p className="muted" style={{ fontSize: 13 }}>{t("cctvFileHint")}</p>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/*" onChange={(e) => senseFile(e.target.files?.[0])} />
        </div>
      )}

      <details className="field-more">
        <summary>{t("fieldMore")}</summary>
        <p className="muted" style={{ fontSize: 14 }}>{t("cctvSnapHint")}</p>
        {mode === "HTTP" && (
          <label className="field-bus">
            <span>{t("cctvSnapUrl")}</span>
            <input value={snapUrl} onChange={(e) => setSnapUrl(e.target.value)} placeholder="depot only" />
          </label>
        )}
        <div className="field-row">
          <button className="btn ghost" type="button" onClick={() => setMode("HTTP")}>{t("cctvModeHTTP")}</button>
          <button className="btn ghost" type="button" onClick={() => setMode("DEMO")}>{t("cctvModeDEMO")}</button>
        </div>
        {mode === "HTTP" && <button className="btn folio-stamp" type="button" disabled={!!busy || !snapUrl} onClick={sensePull}>{t("cctvPull")}</button>}
        {mode === "DEMO" && <button className="btn folio-stamp" type="button" disabled={!!busy} onClick={senseDemo}>{t("cctvDemo")}</button>}
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
        <p className="muted" style={{ fontSize: 13 }}>{t("cctvScript")}</p>
      </details>

      <div className="field-row">
        {mode === "LENS" && (
          <button className="chip" type="button" aria-pressed={patrol} onClick={() => setPatrol((on) => !on)}>
            {patrol ? t("fieldAuto") : t("fieldManual")}
          </button>
        )}
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
      <p className="muted field-honest">{t("cctvHonest")}</p>
    </div>
  );
}
