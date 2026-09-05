import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import DetectionOverlay from "../components/DetectionOverlay.jsx";
import { useFieldOverlay } from "../field/useFieldOverlay.js";
import { api, getScope, getToken, setSession, wsUrl } from "../api";
import { useUi } from "../i18n.jsx";

function fieldOrigin() {
  return window.location.origin;
}

function asBusCode(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  if (digits) return `BUS-${digits.padStart(3, "0")}`;
  const up = String(raw || "").toUpperCase();
  return up.startsWith("BUS-") ? up : "BUS-017";
}

export default function FieldCamera() {
  const { t, lang, toggleLang } = useUi();
  const [params] = useSearchParams();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [authed, setAuthed] = useState(() => Boolean(getToken()) && getScope() === "field");
  const [code, setCode] = useState(params.get("code") || "");
  const [joinErr, setJoinErr] = useState("");
  const [joining, setJoining] = useState(false);
  const [ping, setPing] = useState(null);
  const [camErr, setCamErr] = useState("");
  const [facing, setFacing] = useState("environment");
  const [busNum, setBusNum] = useState(() => {
    const raw = params.get("bus") || "17";
    return String(raw).replace(/\D/g, "") || "17";
  });
  const [slot, setSlot] = useState(() => {
    const n = Number(params.get("phone") || 1);
    return n >= 1 && n <= 4 ? n : 1;
  });
  const busId = asBusCode(busNum);
  const sourceId = `${busId}-P${slot}`;
  const [fix, setFix] = useState(null);
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [boxes, setBoxes] = useState([]);
  const [patrol, setPatrol] = useState(true);
  const lastIngest = useRef(0);
  const lastShake = useRef(0);
  const busyRef = useRef("");
  const [imu, setImu] = useState(null);
  const imuRef = useRef(null);
  const fixRef = useRef(null);

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
    const here = fixRef.current;
    const lat = here?.lat ?? 28.6328;
    const lng = here?.lng ?? 77.2195;
    const still = new FormData();
    still.append("file", blob, "field-still.jpg");
    still.append("latitude", String(lat));
    still.append("longitude", String(lng));
    if (here?.acc) still.append("gps_accuracy", String(Number(here.acc).toFixed(1)));
    still.append("source_id", sourceId);
    still.append("bus_id", busId);
    still.append("camera_bay", facing === "user" ? "CABIN" : "FRONT");
    if (here?.heading != null) still.append("heading", String(here.heading));
    if (here?.speed != null) still.append("speed_kmh", String(Number(here.speed).toFixed(1)));
    if (imuRef.current != null) still.append("imu_mag", String(Number(imuRef.current).toFixed(2)));
    return api("/ingest/phone/still", { method: "POST", body: still });
  }

  const overlay = useFieldOverlay({
    authed,
    patrol,
    videoRef,
    blobFromVideo,
    postStill,
    setBoxes,
    setResult,
    onError: setErr,
  });

  useEffect(() => {
    let watch = 0;
    if (!navigator.geolocation) return undefined;
    navigator.geolocation.getCurrentPosition(
      (pos) => setFix({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        acc: pos.coords.accuracy,
        heading: Number.isFinite(pos.coords.heading) ? pos.coords.heading : null,
        speed: Number.isFinite(pos.coords.speed) ? pos.coords.speed * 3.6 : null,
      }),
      () => {},
      { enableHighAccuracy: true, timeout: 12000 },
    );
    watch = navigator.geolocation.watchPosition(
      (pos) => setFix({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        acc: pos.coords.accuracy,
        heading: Number.isFinite(pos.coords.heading) ? pos.coords.heading : null,
        speed: Number.isFinite(pos.coords.speed) ? pos.coords.speed * 3.6 : null,
      }),
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
    const beat = () => {
      api("/sensor-nodes/heartbeat", {
        method: "POST",
        body: JSON.stringify({
          sensor_code: sourceId,
          bus_code: busId,
          camera_status: streamRef.current ? "ONLINE" : "DEGRADED",
          gps_status: fixRef.current ? "ONLINE" : "DEGRADED",
          imu_status: imuRef.current != null ? "ONLINE" : "UNKNOWN",
          network_type: "CELL",
          ai_mode: patrol ? "AUTO" : "MANUAL",
          latitude: fixRef.current?.lat ?? 28.6328,
          longitude: fixRef.current?.lng ?? 77.2195,
          heading: fixRef.current?.heading ?? null,
          speed_kmh: fixRef.current?.speed ?? null,
          last_boxes: [...(overlay.lastBoxes.current || []), ...(overlay.lastPeople.current || [])],
          person_count: (overlay.lastPeople.current || []).length,
          overlay_fps: overlay.fpsRef?.current || 0,
          overlay_mode: overlay.mode,
          overlay_backend: overlay.backendRef?.current || overlay.backend,
          infer_ms: overlay.inferMsRef?.current || overlay.inferMs || 0,
        }),
      }).catch(() => {});
    };
    beat();
    const id = window.setInterval(beat, 500);
    return () => window.clearInterval(id);
  }, [authed, busNum, slot, patrol, overlay.mode]);

  useEffect(() => {
    if (!authed) return undefined;
    const token = getToken();
    if (!token) return undefined;
    const sock = new WebSocket(wsUrl("/ws/field-live", token));
    let timer = 0;
    sock.onopen = () => {
      timer = window.setInterval(() => {
        if (sock.readyState !== 1) return;
        sock.send(JSON.stringify({
          sensor_code: sourceId,
          bus_code: busId,
          latitude: fixRef.current?.lat ?? 28.6328,
          longitude: fixRef.current?.lng ?? 77.2195,
          heading: fixRef.current?.heading ?? null,
          last_boxes: [...(overlay.lastBoxes.current || []), ...(overlay.lastPeople.current || [])],
          person_count: (overlay.lastPeople.current || []).length,
          overlay_fps: overlay.fpsRef?.current || 0,
          overlay_mode: overlay.mode,
          overlay_backend: overlay.backendRef?.current || overlay.backend,
          infer_ms: overlay.inferMsRef?.current || overlay.inferMs || 0,
          ai_mode: patrol ? "AUTO" : "MANUAL",
        }));
      }, 250);
    };
    return () => {
      if (timer) window.clearInterval(timer);
      sock.close();
    };
  }, [authed, busNum, slot, patrol, overlay.mode, sourceId, busId]);

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
          video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } },
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

  async function senseStill(blob) {
    setErr("");
    setResult(null);
    setBusy("still");
    try {
      const jpeg = blob instanceof Blob ? blob : await blobFromVideo();
      const ingested = await postStill(jpeg);
      const ev = ingested.event || {};
      const found = ingested.detections || ev.extra?.detections || [];
      setBoxes(found);
      lastIngest.current = Date.now();
      setResult({
        path: (ingested.observation?.extra?.ai_status) || "RULE_BASED",
        title: ev.public_code,
        type: ev.event_type,
        created: ingested.created_event,
        patrol: ev.extra?.patrol_state,
        eventId: ev.id,
        note: found.length
          ? `Azure RDD · ${found.length} box(es). Pin is ahead on the road, not under the phone.`
          : "Still stored. Azure RDD found no box on this frame.",
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

  async function emitShake() {
    const now = Date.now();
    if (now - lastShake.current < 12000) return;
    lastShake.current = now;
    const here = fixRef.current;
    const speed = here?.speed ?? 0;
    const kind = speed >= 45 ? "RASH_DRIVING" : "POTHOLE";
    try {
      const ingested = await api("/ingest/phone", {
        method: "POST",
        body: JSON.stringify({
          event_type: kind,
          severity: "HIGH",
          latitude: here?.lat ?? 28.6328,
          longitude: here?.lng ?? 77.2195,
          gps_accuracy: here?.acc ?? null,
          source_type: "PHONE",
          source_id: sourceId,
          bus_id: busId,
          heading: here?.heading ?? null,
          speed_kmh: speed || null,
          confidence: 0.5,
          simulated: false,
          extra: {
            method: "phone-imu-shake",
            ai_status: "RULE_BASED",
            engine_status: "RULE_BASED",
            patrol: true,
            imu_mag: imuRef.current,
            camera_bay: bay(),
            derivation: "Accelerometer spike. Proximity is near/far only. Not a crash net.",
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
        note: kind === "RASH_DRIVING"
          ? "Suspicious shake at speed. IMU rule, not a rash-driving neural net."
          : "Hard shake while slow — treated as a bump/pothole hit. IMU rule.",
        raw: ingested,
      });
    } catch {
      /* keep patrol alive */
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
          sensor_code: sourceId,
          bus_code: busId,
          camera_status: streamRef.current ? "ONLINE" : "DEGRADED",
          gps_status: fix ? "ONLINE" : "DEGRADED",
          imu_status: imuRef.current != null ? "ONLINE" : "UNKNOWN",
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

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    imuRef.current = imu;
  }, [imu]);

  useEffect(() => {
    fixRef.current = fix;
  }, [fix]);

  useEffect(() => {
    if (!authed) return undefined;
    let dead = false;
    async function arm() {
      try {
        if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
          await DeviceMotionEvent.requestPermission();
        }
      } catch {
        /* iPhone may deny; GPS still works */
      }
    }
    arm();
    function onMotion(e) {
      if (dead) return;
      const raw = e.acceleration || e.accelerationIncludingGravity;
      if (!raw) return;
      const mag = Math.hypot(raw.x || 0, raw.y || 0, raw.z || 0);
      const shown = e.acceleration ? mag + 9.8 : mag;
      setImu(shown);
      if (shown >= 16) emitShake();
    }
    window.addEventListener("devicemotion", onMotion);
    return () => {
      dead = true;
      window.removeEventListener("devicemotion", onMotion);
    };
  }, [authed, busNum, slot]);

  const step = !authed ? 1 : 2;

  if (!authed) {
    return (
      <div className="field-shell">
        <header className="field-head">
          <div>
            <div className="folio-brand">SADAKSAARTHI</div>
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
          <p className="how-kicker">{t("howTitle")}</p>
          <ol className="how-simple">
            <li>{t("how1")}</li>
            <li>{t("how2")}</li>
            <li>{t("how3")}</li>
            <li>{t("how4")}</li>
          </ol>
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
          <label htmlFor="booth-bus">{t("fieldBusNum")}</label>
          <input
            id="booth-bus"
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
          <button className="btn folio-stamp" type="submit" disabled={joining || code.length < 6 || !busNum}>
            {joining ? "…" : t("fieldPing")}
          </button>
          <p className="muted" style={{ fontSize: 14 }}>{t("fieldHttps")}</p>
        </form>
      </div>
    );
  }

  return (
    <div className="field-shell">
      <header className="field-head">
        <div>
          <div className="folio-brand">SADAKSAARTHI</div>
          <div className="folio-brand-sub">{t("fieldUnit")}</div>
        </div>
        <div className="field-head-actions">
          <button className="lang-toggle" type="button" aria-pressed={lang === "hi"} onClick={toggleLang}>{t("lang")}</button>
          <span className="muted">Phone booth</span>
        </div>
      </header>
      <ol className="field-steps" aria-label="Field booth steps">
        <li>{t("fieldStepPin")}</li>
        <li className={step === 2 ? "is-on" : ""}>{t("fieldStepLens")}</li>
        <li className={step === 3 ? "is-on" : ""}>{t("fieldStepFolio")}</li>
      </ol>

      <div className="field-status" role="status">
        <span className="tag real">{busId}</span>
        <span className="tag info">{t("fieldPhoneN")} {slot}</span>
        <span className={`tag ${patrol ? "real" : "rule"}`}>{patrol ? t("fieldAuto") : t("fieldManual")}</span>
        <span className={`tag ${overlay.mode === "ondevice" ? "real" : overlay.mode === "cloud" ? "rule" : "off"}`}>
          {overlay.mode === "ondevice" ? t("fieldOnDevice") : overlay.mode === "cloud" ? t("fieldCloudPreview") : t("fieldWait")}
        </span>
        {overlay.mode === "ondevice" && overlay.backend ? (
          <span className="tag info">{overlay.backend === "webgpu" ? "WEBGPU" : "WASM"}</span>
        ) : null}
        {overlay.mode === "ondevice" && overlay.inferMs > 0 ? (
          <span className="tag info">{overlay.inferMs} ms</span>
        ) : null}
        <span className="tag info">{t("fieldPeople")} {overlay.personCount}</span>
        <span className={`tag ${ping?.health?.status === "ok" ? "real" : "off"}`}>
          {ping?.health?.status === "ok" ? t("fieldOnline") : t("fieldWait")}
        </span>
      </div>

      <div className="field-stage">
        <video ref={videoRef} className="field-video" playsInline muted autoPlay />
        <DetectionOverlay boxes={boxes} />
        {camErr && (
          <div className="field-cam-fallback">
            <p>{camErr}</p>
            <p className="muted">{t("fieldFileHint")}</p>
          </div>
        )}
      </div>

      <div className="field-controls">
        <div className="phone-slots">
          <button className={`chip ${!patrol ? "active" : ""}`} type="button" aria-pressed={!patrol} onClick={() => setPatrol(false)}>{t("fieldManual")}</button>
          <button className={`chip ${patrol ? "active" : ""}`} type="button" aria-pressed={patrol} onClick={() => setPatrol(true)}>{t("fieldAuto")}</button>
        </div>
        <button className="btn folio-stamp field-sense" type="button" disabled={!!busy} onClick={() => senseStill()}>
          {busy === "still" ? "…" : t("fieldSense")}
        </button>
        {err && <div role="alert" className="err">{err}</div>}
        {result && (
          <div className="field-result">
            <div className="field-result-top">
              <span className={`tag ${result.path === "REAL" ? "real" : "rule"}`}>{result.path}</span>
              <b className="mono">{result.title}</b>
            </div>
            <p>{result.type}</p>
            <p className="muted">{result.note}</p>
          </div>
        )}
        <details className="field-more">
          <summary>{t("fieldMore")}</summary>
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
            <button className="chip" type="button" onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}>
              {facing === "environment" ? t("fieldRoadLens") : t("fieldCabinLens")}
            </button>
          </div>
        </details>
        <p className="muted field-honest">{t("fieldHonest")}</p>
      </div>
    </div>
  );
}
