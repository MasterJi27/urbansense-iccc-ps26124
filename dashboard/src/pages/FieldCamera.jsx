import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, getScope, getToken, setSession } from "../api";
import { useUi } from "../i18n.jsx";

function fieldOrigin() {
  return window.location.origin;
}

export default function FieldCamera() {
  const { t, lang, toggleLang } = useUi();
  const [params] = useSearchParams();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [authed, setAuthed] = useState(!!getToken());
  const [code, setCode] = useState(params.get("code") || "");
  const [joinErr, setJoinErr] = useState("");
  const [joining, setJoining] = useState(false);
  const [ping, setPing] = useState(null);
  const [camErr, setCamErr] = useState("");
  const [facing, setFacing] = useState("environment");
  const [busId, setBusId] = useState(params.get("bus") || "FIELD-IPHONE");
  const [fix, setFix] = useState(null);
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let watch = 0;
    if (!navigator.geolocation) return undefined;
    navigator.geolocation.getCurrentPosition(
      (pos) => setFix({ lat: pos.coords.latitude, lng: pos.coords.longitude, acc: pos.coords.accuracy }),
      () => {},
      { enableHighAccuracy: true, timeout: 12000 },
    );
    watch = navigator.geolocation.watchPosition(
      (pos) => setFix({ lat: pos.coords.latitude, lng: pos.coords.longitude, acc: pos.coords.accuracy }),
      () => {},
      { enableHighAccuracy: true, maximumAge: 4000 },
    );
    return () => {
      if (watch) navigator.geolocation.clearWatch(watch);
    };
  }, []);

  useEffect(() => {
    if (!authed) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const healthUrl = import.meta.env.DEV ? "/api/health" : `${fieldOrigin()}/health`;
        const health = await fetch(healthUrl).then((r) => r.json());
        const me = await api("/auth/me").catch(() => null);
        if (!cancelled) setPing({ health, me });
      } catch {
        if (!cancelled) setPing({ health: { status: "unreachable" }, me: null });
      }
    })();
    return () => { cancelled = true; };
  }, [authed]);

  useEffect(() => {
    if (!authed) return undefined;
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
          video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } },
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
        if (!dead) setCamErr(ex.message || "Camera denied. iPhone needs HTTPS (Azure) or a file still.");
      }
    })();
    return () => {
      dead = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((tr) => tr.stop());
        streamRef.current = null;
      }
    };
  }, [authed, facing]);

  async function join(e) {
    e.preventDefault();
    setJoinErr("");
    setJoining(true);
    try {
      const data = await api("/auth/field-join", { method: "POST", body: JSON.stringify({ code: code.trim() }) });
      setSession(data);
      setAuthed(true);
    } catch (ex) {
      setJoinErr(ex.message);
    } finally {
      setJoining(false);
    }
  }

  function bay() {
    return facing === "user" ? "CABIN" : "FRONT";
  }

  async function blobFromVideo() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) throw new Error("Camera not ready");
    const max = 1280;
    const scale = Math.min(1, max / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("JPEG encode failed"))), "image/jpeg", 0.72);
    });
  }

  async function postStill(blob) {
    const lat = fix?.lat ?? 28.6328;
    const lng = fix?.lng ?? 77.2195;
    const still = new FormData();
    still.append("file", blob, "field-still.jpg");
    still.append("latitude", String(lat));
    still.append("longitude", String(lng));
    if (fix?.acc) still.append("gps_accuracy", String(Number(fix.acc).toFixed(1)));
    still.append("source_id", busId || "FIELD-IPHONE");
    if (busId.startsWith("BUS-")) still.append("bus_id", busId);
    still.append("camera_bay", bay());
    return api("/ingest/phone/still", { method: "POST", body: still });
  }

  async function senseStill(blob) {
    setErr("");
    setResult(null);
    setBusy("still");
    try {
      const jpeg = blob instanceof Blob ? blob : await blobFromVideo();
      const ingested = await postStill(jpeg);
      const ev = ingested.event || {};
      setResult({
        path: (ingested.observation?.extra?.ai_status) || "RULE_BASED",
        title: ev.public_code,
        type: ev.event_type,
        created: ingested.created_event,
        patrol: ev.extra?.patrol_state,
        eventId: ev.id,
        note: "One still stored. Not a video stream. Azure Vision if configured; otherwise OTHER / IMU fallback.",
        raw: ingested,
      });
    } catch (ex) {
      const msg = ex.message === "Internal Server Error"
        ? "Sense failed on the server. Try TAP again, or pick a photo below."
        : ex.message;
      setErr(msg);
      if (!getToken()) setAuthed(false);
    } finally {
      setBusy("");
    }
  }

  async function tapWater() {
    setErr("");
    setResult(null);
    setBusy("water");
    try {
      const ingested = await api("/ingest/phone", {
        method: "POST",
        body: JSON.stringify({
          event_type: "WATERLOGGING",
          severity: "HIGH",
          latitude: fix?.lat ?? 28.6328,
          longitude: fix?.lng ?? 77.2195,
          gps_accuracy: fix?.acc ?? null,
          source_type: "PHONE",
          source_id: busId,
          bus_id: busId.startsWith("BUS-") ? busId : null,
          confidence: 0.55,
          simulated: false,
          extra: {
            method: "field-tap",
            ai_status: "RULE_BASED",
            engine_status: "RULE_BASED",
            patrol: true,
            camera_bay: bay(),
            derivation: "Human field tap with GPS. Not a waterlogging neural net.",
          },
        }),
      });
      const ev = ingested.event || {};
      setResult({
        path: "RULE_BASED",
        title: ev.public_code,
        type: ev.event_type,
        created: ingested.created_event,
        patrol: ev.extra?.patrol_state,
        eventId: ev.id,
        note: "Waterlogging tap is RULE_BASED. We do not ship a flood detector.",
        raw: ingested,
      });
    } catch (ex) {
      setErr(ex.message);
      if (!getToken()) setAuthed(false);
    } finally {
      setBusy("");
    }
  }

  async function clearPass() {
    setErr("");
    setResult(null);
    setBusy("clear");
    try {
      const body = await api("/sensor-nodes/heartbeat", {
        method: "POST",
        body: JSON.stringify({
          sensor_code: `FIELD-${busId}`,
          bus_code: busId.startsWith("BUS-") ? busId : null,
          camera_status: streamRef.current ? "ONLINE" : "DEGRADED",
          gps_status: fix ? "ONLINE" : "DEGRADED",
          imu_status: "UNKNOWN",
          network_type: "CELL",
          ai_mode: "FIELD_WEB",
          latitude: fix?.lat ?? 28.6328,
          longitude: fix?.lng ?? 77.2195,
        }),
      });
      setResult({
        path: "RULE_BASED",
        title: "CLEAR HEARTBEAT",
        type: "ABSENCE",
        note: "Later independent heartbeats can expire a rumour or audit a repair. This phone is one pass.",
        raw: body,
      });
    } catch (ex) {
      setErr(ex.message);
      if (!getToken()) setAuthed(false);
    } finally {
      setBusy("");
    }
  }

  const step = !authed ? 1 : result ? 3 : 2;
  const icccLinked = getScope() !== "field";

  if (!authed) {
    return (
      <div className="field-shell">
        <header className="field-head">
          <div>
            <div className="folio-brand">URBANSENSE</div>
            <div className="folio-brand-sub">{t("fieldUnit")}</div>
          </div>
          <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>{t("lang")}</button>
        </header>
        <ol className="field-steps" aria-label="Field booth steps">
          <li className={step === 1 ? "is-on" : ""}>{t("fieldStepPin")}</li>
          <li>{t("fieldStepLens")}</li>
          <li>{t("fieldStepFolio")}</li>
        </ol>
        <form className="field-join" onSubmit={join}>
          <h1>{t("fieldJoinTitle")}</h1>
          <p className="muted">{t("fieldJoinSub")}</p>
          <label htmlFor="booth-code">{t("fieldPin")}</label>
          <input
            id="booth-code"
            className="field-pin"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="428193"
          />
          {joinErr && <div role="alert" className="err">{joinErr}</div>}
          <button className="btn folio-stamp" type="submit" disabled={joining || code.length < 6}>
            {joining ? "…" : t("fieldPing")}
          </button>
          <p className="muted" style={{ fontSize: 12 }}>{t("fieldHttps")}</p>
          <Link className="muted" to="/login?next=/field">{t("fieldIcccLogin")}</Link>
        </form>
      </div>
    );
  }

  return (
    <div className="field-shell">
      <header className="field-head">
        <div>
          <div className="folio-brand">URBANSENSE</div>
          <div className="folio-brand-sub">{t("fieldUnit")}</div>
        </div>
        <div className="field-head-actions">
          <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>{t("lang")}</button>
          {icccLinked ? <Link className="field-link" to="/">{t("fieldBackIccc")}</Link> : <span className="muted">Booth token</span>}
        </div>
      </header>
      <ol className="field-steps" aria-label="Field booth steps">
        <li>{t("fieldStepPin")}</li>
        <li className={step === 2 ? "is-on" : ""}>{t("fieldStepLens")}</li>
        <li className={step === 3 ? "is-on" : ""}>{t("fieldStepFolio")}</li>
      </ol>

      <div className="field-status" role="status">
        <span className={`tag ${ping?.health?.status === "ok" ? "real" : "off"}`}>
          {ping?.health?.status === "ok" ? "SERVER PING OK" : "PING…"}
        </span>
        <span className={`tag ${fix ? "real" : "sim"}`}>{fix ? `GPS ${fix.acc ? `${Math.round(fix.acc)}m` : "FIX"}` : "GPS…"}</span>
        <span className={`tag ${camErr ? "off" : "rule"}`}>{camErr ? "CAMERA" : `${bay()} LENS`}</span>
      </div>

      <div className="field-stage">
        <video ref={videoRef} className="field-video" playsInline muted autoPlay />
        {camErr && (
          <div className="field-cam-fallback">
            <p>{camErr}</p>
            <p className="muted">{t("fieldFileHint")}</p>
          </div>
        )}
      </div>

      <div className="field-controls">
        <label className="field-bus">
          <span>{t("fieldBus")}</span>
          <input value={busId} onChange={(e) => setBusId(e.target.value.toUpperCase())} />
        </label>
        <button
          className="chip"
          type="button"
          aria-pressed={facing === "environment"}
          onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
        >
          {facing === "environment" ? t("fieldRoadLens") : t("fieldCabinLens")}
        </button>
        <button className="btn folio-stamp field-sense" type="button" disabled={!!busy} onClick={() => senseStill()}>
          {busy === "still" ? "…" : t("fieldSense")}
        </button>
        <label className="field-file">
          <span>{t("fieldPickPhoto")}</span>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            disabled={!!busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) senseStill(file);
              e.target.value = "";
            }}
          />
        </label>
        <div className="field-row">
          <button className="btn ghost" type="button" disabled={!!busy} onClick={tapWater}>{busy === "water" ? "…" : t("fieldWater")}</button>
          <button className="btn ghost" type="button" disabled={!!busy} onClick={clearPass}>{busy === "clear" ? "…" : t("fieldClear")}</button>
        </div>
        {err && <div role="alert" className="err">{err}</div>}
        {result && (
          <div className="field-result">
            <div className="field-result-top">
              <span className={`tag ${result.path === "REAL" ? "real" : "rule"}`}>{result.path}</span>
              <b className="mono">{result.title}</b>
              {result.created ? <span className="tag info">FIRST_SIGHTING</span> : result.title ? <span className="tag real">FUSED</span> : null}
            </div>
            <p>{result.type}{result.patrol ? ` · ${result.patrol}` : ""}</p>
            <p className="muted">{result.note}</p>
            {result.eventId && <Link to={`/events/${result.eventId}`}>{t("fieldOpenEvent")}</Link>}
          </div>
        )}
        <p className="muted field-honest">{t("fieldHonest")}</p>
      </div>
    </div>
  );
}
