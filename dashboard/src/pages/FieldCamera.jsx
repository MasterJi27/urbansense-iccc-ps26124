import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import DetectionOverlay from "../components/DetectionOverlay.jsx";
import FieldPulse from "../field/FieldPulse.jsx";
import { CADENCE_IDS, isPatrol } from "../field/cadence.js";
import { useFieldOverlay } from "../field/useFieldOverlay.js";
import { startLiveBuffer, vpnHint, readNetwork } from "../field/livePhoto.js";
import { api, getScope, getToken, setSession, wsUrl } from "../api";
import { useUi } from "../i18n.jsx";

const CADENCE_KEY = "urbansense_field_cadence";

function readCadence() {
  try {
    const stored = sessionStorage.getItem(CADENCE_KEY);
    if (CADENCE_IDS.includes(stored)) return stored;
  } catch {
    /* private mode */
  }
  return "detect";
}

function fieldOrigin() {
  return window.location.origin;
}

function asBusCode(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  if (digits) return `BUS-${digits.padStart(3, "0")}`;
  const up = String(raw || "").toUpperCase();
  return up.startsWith("BUS-") ? up : "BUS-017";
}

function busDigitsFrom(raw) {
  return String(raw || "").replace(/\D/g, "").slice(0, 3);
}

async function requestMotionPermission() {
  try {
    if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
      await DeviceMotionEvent.requestPermission();
    }
  } catch {
    /* iPhone may deny; GPS still works */
  }
  try {
    if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
      await DeviceOrientationEvent.requestPermission();
    }
  } catch {
    /* orientation optional */
  }
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
  const [busNum, setBusNum] = useState(() => busDigitsFrom(params.get("bus")) || "17");
  const [busLocked, setBusLocked] = useState(() => Boolean(params.get("bus")));
  const [slot, setSlot] = useState(() => {
    const n = Number(params.get("phone") || 1);
    return n >= 1 && n <= 4 ? n : 1;
  });
  const busId = asBusCode(busNum);
  const sourceId = `${busId}-P${slot}`;
  const [fix, setFix] = useState(null);
  const [gpsErr, setGpsErr] = useState("");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [boxes, setBoxes] = useState([]);
  const [cadence, setCadence] = useState(readCadence);
  const patrol = isPatrol(cadence);
  const lastIngest = useRef(0);
  const classCountsRef = useRef({ D00: 0, D10: 0, D20: 0, D40: 0 });
  const imuSeriesRef = useRef([]);
  const detSeriesRef = useRef([]);
  const lastPulseAt = useRef(0);
  const [pulse, setPulse] = useState({ imu: [], dets: [], counts: { D00: 0, D10: 0, D20: 0, D40: 0 }, azureMs: 0 });
  const lastShake = useRef(0);
  const busyRef = useRef("");
  const [imu, setImu] = useState(null);
  const imuRef = useRef(null);
  const imuAxesRef = useRef(null);
  const gyroZRef = useRef(null);
  const fixRef = useRef(null);
  const liveBufRef = useRef(null);
  const [serverRtt, setServerRtt] = useState(null);
  const [place, setPlace] = useState(null);

  function lockBusFrom(raw) {
    const digits = busDigitsFrom(raw);
    if (!digits) return;
    setBusNum(digits);
    setBusLocked(true);
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
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("JPEG encode failed"))), "image/jpeg", 0.86);
    });
  }

  async function postStill(blob) {
    const here = fixRef.current;
    if (here?.lat == null || here?.lng == null) {
      throw new Error("Allow location");
    }
    const still = new FormData();
    still.append("file", blob, "field-still.jpg");
    still.append("latitude", String(here.lat));
    still.append("longitude", String(here.lng));
    if (here.acc != null) still.append("gps_accuracy", String(Number(here.acc).toFixed(1)));
    still.append("source_id", sourceId);
    still.append("bus_id", busId);
    still.append("camera_bay", facing === "user" ? "CABIN" : "FRONT");
    if (here.heading != null) still.append("heading", String(here.heading));
    if (here.speed != null) still.append("speed_kmh", String(Number(here.speed).toFixed(1)));
    if (imuRef.current != null) still.append("imu_mag", String(Number(imuRef.current).toFixed(2)));
    const clip = liveBufRef.current?.take?.();
    if (clip && clip.size > 800) {
      const ext = liveBufRef.current.extension?.() || "webm";
      still.append("clip", clip, `live.${ext}`);
    }
    return api("/ingest/phone/still", { method: "POST", body: still });
  }

  function pushPulse(roads) {
    const now = Date.now();
    if (now - lastPulseAt.current < 250) return;
    lastPulseAt.current = now;
    const counts = { ...classCountsRef.current };
    for (const det of roads || []) {
      const id = det.class_id || det.classId;
      if (id && counts[id] != null) counts[id] += 1;
    }
    classCountsRef.current = counts;
    const dets = detSeriesRef.current.concat({ t: now, count: (roads || []).length }).slice(-80);
    detSeriesRef.current = dets;
    setPulse((prev) => ({
      imu: imuSeriesRef.current,
      dets,
      counts,
      azureMs: prev.azureMs,
    }));
  }

  const overlay = useFieldOverlay({
    authed,
    cadence,
    videoRef,
    blobFromVideo,
    postStill,
    setBoxes,
    setResult,
    onError: setErr,
    onPulse: ({ roads }) => pushPulse(roads),
  });

  useEffect(() => {
    if (!navigator.geolocation) {
      setGpsErr("Allow location");
      return undefined;
    }
    const opts = { enableHighAccuracy: true, maximumAge: 1000, timeout: 15000 };
    function onOk(pos) {
      setGpsErr("");
      setFix({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        acc: pos.coords.accuracy,
        heading: Number.isFinite(pos.coords.heading) ? pos.coords.heading : null,
        speed: Number.isFinite(pos.coords.speed) ? pos.coords.speed * 3.6 : null,
      });
    }
    function onBad() {
      setFix(null);
      setGpsErr("Allow location");
    }
    navigator.geolocation.getCurrentPosition(onOk, onBad, opts);
    const watch = navigator.geolocation.watchPosition(onOk, onBad, opts);
    return () => {
      if (watch) navigator.geolocation.clearWatch(watch);
    };
  }, []);

  useEffect(() => {
    if (!authed) return undefined;
    let cancelled = false;
    async function pingOnce() {
      const t0 = performance.now();
      try {
        const healthUrl = import.meta.env.DEV ? "/api/health" : `${fieldOrigin()}/health`;
        const health = await fetch(healthUrl).then((r) => r.json());
        const ms = Math.round(performance.now() - t0);
        const me = await api("/auth/me").catch(() => null);
        if (!cancelled) {
          setServerRtt(ms);
          setPing({ health, me });
        }
      } catch {
        if (!cancelled) {
          setServerRtt(null);
          setPing({ health: { status: "unreachable" }, me: null });
        }
      }
    }
    pingOnce();
    const id = window.setInterval(pingOnce, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [authed]);

  function liveExtras() {
    const here = fixRef.current;
    const hasGps = here?.lat != null && here?.lng != null;
    const body = {
      sensor_code: sourceId,
      bus_code: busId,
      camera_status: streamRef.current ? "ONLINE" : "DEGRADED",
      gps_status: hasGps ? "ONLINE" : "DEGRADED",
      gps_ok: hasGps,
      imu_status: imuRef.current != null ? "ONLINE" : "UNKNOWN",
      network_type: readNetwork().type,
      ai_mode: patrol ? `AUTO:${cadence}` : "MANUAL",
      last_boxes: [...(overlay.lastBoxes.current || []), ...(overlay.lastPeople.current || [])],
      person_count: (overlay.lastPeople.current || []).length,
      overlay_fps: overlay.fpsRef?.current || 0,
      overlay_mode: overlay.mode,
      overlay_backend: overlay.backendRef?.current || overlay.backend,
      infer_ms: overlay.inferMsRef?.current || overlay.inferMs || 0,
    };
    if (hasGps) {
      body.latitude = here.lat;
      body.longitude = here.lng;
      if (here.acc != null) body.gps_accuracy = here.acc;
      if (here.heading != null) body.heading = here.heading;
      if (here.speed != null) body.speed_kmh = here.speed;
    }
    if (imuRef.current != null) body.imu_mag = imuRef.current;
    const axes = imuAxesRef.current;
    if (axes) {
      if (axes.ax != null) body.imu_ax = axes.ax;
      if (axes.ay != null) body.imu_ay = axes.ay;
      if (axes.az != null) body.imu_az = axes.az;
    }
    if (gyroZRef.current != null) body.gyro_z = gyroZRef.current;
    return body;
  }

  useEffect(() => {
    if (!authed) return undefined;
    const beat = () => {
      api("/sensor-nodes/heartbeat", {
        method: "POST",
        body: JSON.stringify(liveExtras()),
      }).catch(() => {});
    };
    beat();
    const id = window.setInterval(beat, 500);
    return () => window.clearInterval(id);
  }, [authed, busNum, slot, patrol, cadence, overlay.mode]);

  useEffect(() => {
    if (!authed) return undefined;
    const token = getToken();
    if (!token) return undefined;
    const sock = new WebSocket(wsUrl("/ws/field-live", token));
    let timer = 0;
    sock.onopen = () => {
      timer = window.setInterval(() => {
        if (sock.readyState !== 1) return;
        sock.send(JSON.stringify(liveExtras()));
      }, 250);
    };
    return () => {
      if (timer) window.clearInterval(timer);
      sock.close();
    };
  }, [authed, busNum, slot, patrol, cadence, overlay.mode, sourceId, busId]);

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

  useEffect(() => {
    if (!authed) return undefined;
    if (liveBufRef.current) liveBufRef.current.stop();
    liveBufRef.current = startLiveBuffer(() => streamRef.current, cadence === "track1s" ? 1100 : 2200);
    return () => {
      if (liveBufRef.current) {
        liveBufRef.current.stop();
        liveBufRef.current = null;
      }
    };
  }, [authed, facing, cadence]);

  async function join(e) {
    e.preventDefault();
    setJoinErr("");
    setJoining(true);
    await requestMotionPermission();
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setGpsErr("");
          setFix({
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            acc: pos.coords.accuracy,
            heading: Number.isFinite(pos.coords.heading) ? pos.coords.heading : null,
            speed: Number.isFinite(pos.coords.speed) ? pos.coords.speed * 3.6 : null,
          });
        },
        () => {
          setFix(null);
          setGpsErr("Allow location");
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
      );
    }
    try {
      const data = await api("/auth/field-join", { method: "POST", body: JSON.stringify({ code: code.trim() }) });
      setSession(data);
      if (data.bus_code) lockBusFrom(data.bus_code);
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
    const here = fixRef.current;
    if (here?.lat == null || here?.lng == null) {
      setErr("Allow location");
      return;
    }
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
        live: Boolean(ev.extra?.live_photo_url),
        place: ev.extra?.place?.label,
        azureMs: ev.extra?.azure_still_ms || ev.extra?.rdd_infer_ms,
        note: found.length
          ? `Report ${ev.public_code} · ${found.length} box(es)${ev.extra?.azure_still_ms ? ` · Azure ${ev.extra.azure_still_ms} ms` : ""}. Hold the still on ICCC to play the live clip.`
          : "Report stored. Azure RDD found no box on this frame.",
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
    if (here?.lat == null || here?.lng == null) return;
    const speed = here.speed ?? 0;
    const kind = speed >= 45 ? "RASH_DRIVING" : "POTHOLE";
    try {
      const ingested = await api("/ingest/phone", {
        method: "POST",
        body: JSON.stringify({
          event_type: kind,
          severity: "HIGH",
          latitude: here.lat,
          longitude: here.lng,
          gps_accuracy: here.acc ?? null,
          source_type: "PHONE",
          source_id: sourceId,
          bus_id: busId,
          heading: here.heading ?? null,
          speed_kmh: speed || null,
          confidence: 0.5,
          simulated: false,
          extra: {
            method: "phone-imu-shake",
            ai_status: "RULE_BASED",
            engine_status: "RULE_BASED",
            patrol: true,
            imu_mag: imuRef.current,
            gyro_z: gyroZRef.current,
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
          ...liveExtras(),
          ai_mode: "FIELD_WEB",
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
    if (result?.azureMs) {
      setPulse((prev) => ({ ...prev, azureMs: result.azureMs }));
    }
  }, [result]);

  function chooseCadence(id) {
    setCadence(id);
    try {
      sessionStorage.setItem(CADENCE_KEY, id);
    } catch {
      /* private mode */
    }
    if (id !== "manual") requestMotionPermission();
  }

  useEffect(() => {
    if (!authed || fix?.lat == null || fix?.lng == null) {
      setPlace(null);
      return undefined;
    }
    let cancelled = false;
    api(`/maps/place?lat=${encodeURIComponent(fix.lat)}&lon=${encodeURIComponent(fix.lng)}`)
      .then((body) => {
        if (!cancelled) setPlace(body);
      })
      .catch(() => {
        if (!cancelled) setPlace(null);
      });
    return () => {
      cancelled = true;
    };
  }, [authed, fix?.lat, fix?.lng]);

  useEffect(() => {
    if (!authed) return undefined;
    let dead = false;
    function onMotion(e) {
      if (dead) return;
      const raw = e.accelerationIncludingGravity || e.acceleration;
      if (raw) {
        const ax = raw.x || 0;
        const ay = raw.y || 0;
        const az = raw.z || 0;
        imuAxesRef.current = { ax, ay, az };
        const mag = Math.hypot(ax, ay, az);
        setImu(mag);
        imuSeriesRef.current = imuSeriesRef.current.concat({ t: Date.now(), mag }).slice(-80);
        if (mag >= 16) emitShake();
      }
      const rz = e.rotationRate?.alpha;
      if (Number.isFinite(rz)) gyroZRef.current = rz;
    }
    function onOrient() {
      /* iOS pairs DeviceOrientation permission with motion; heading stays GPS. */
    }
    window.addEventListener("devicemotion", onMotion);
    window.addEventListener("deviceorientation", onOrient);
    return () => {
      dead = true;
      window.removeEventListener("devicemotion", onMotion);
      window.removeEventListener("deviceorientation", onOrient);
    };
  }, [authed, busNum, slot]);

  const step = !authed ? 1 : 2;
  const hasGps = fix?.lat != null && fix?.lng != null;
  const net = readNetwork();
  const vpn = vpnHint(fix?.lat, fix?.lng);

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
            <li>{busLocked ? t("how2locked") : t("how2")}</li>
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
          {busLocked ? (
            <p className="muted" style={{ fontSize: 15, margin: 0 }}>
              {t("fieldBusLocked")} <b className="mono">{busId}</b>
            </p>
          ) : (
            <>
              <label htmlFor="booth-bus">{t("fieldBusNum")}</label>
              <input
                id="booth-bus"
                className="field-num"
                inputMode="numeric"
                value={busNum}
                onChange={(e) => setBusNum(e.target.value.replace(/\D/g, "").slice(0, 3))}
                placeholder="17"
              />
            </>
          )}
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
          <span className="tag info">{t("fieldInfer")} {overlay.inferMs} ms</span>
        ) : null}
        <span className={`tag ${ping?.health?.status === "ok" ? "real" : "off"}`}>
          {ping?.health?.status === "ok" ? `${t("fieldOnline")} ${serverRtt != null ? `${serverRtt} ms` : ""}` : t("fieldWait")}
        </span>
        <span className="tag info">{net.label}{net.downlink != null ? ` ${net.downlink.toFixed(1)} Mb/s` : ""}{net.rtt != null ? ` · ${net.rtt} ms` : ""}</span>
        <span className={`gps-chip ${hasGps ? "is-ok" : "is-bad"}`}>
          {hasGps
            ? `${t("fieldGps")} ${fix.lat.toFixed(5)}, ${fix.lng.toFixed(5)} ±${Number(fix.acc || 0).toFixed(0)} m`
            : (gpsErr || "Allow location")}
        </span>
        {place?.label ? <span className="tag info">{place.locality || place.label}</span> : null}
        {vpn ? <span className="tag off">{t("fieldVpn")}</span> : null}
        {imu != null ? <span className="tag info">IMU {imu.toFixed(1)}</span> : null}
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
        <p className="field-cadence-kicker">{t("fieldCadenceTitle")}</p>
        <p className="muted field-cadence-hint">{t("fieldCadenceJury")}</p>
        <div className="field-cadence" role="radiogroup" aria-label={t("fieldCadenceTitle")}>
          {CADENCE_IDS.map((id) => (
            <button
              key={id}
              className={`chip ${cadence === id ? "active" : ""} ${id === "track1s" ? "is-heavy" : ""}`}
              type="button"
              role="radio"
              aria-checked={cadence === id}
              onClick={() => chooseCadence(id)}
            >
              {t(`fieldCadence_${id}`)}
            </button>
          ))}
        </div>
        <p className="muted field-cadence-hint">{t(`fieldCadenceHint_${cadence}`)}</p>
        <button className="btn folio-stamp field-sense" type="button" disabled={!!busy || !hasGps} onClick={() => senseStill()}>
          {busy === "still" ? "…" : (patrol ? t("fieldSense") : t("fieldReportNow"))}
        </button>
        {!hasGps && <div role="alert" className="err">{gpsErr || "Allow location"}</div>}
        {err && <div role="alert" className="err">{err}</div>}
        {result && (
          <div className="field-result">
            <div className="field-result-top">
              <span className={`tag ${result.path === "REAL" ? "real" : "rule"}`}>{result.path}</span>
              <b className="mono">{result.title}</b>
            </div>
            <p>{result.type}</p>
            <p className="muted">{result.note}</p>
            {result.place ? <p className="muted">{result.place}</p> : null}
            {result.live ? <p className="muted">{t("fieldLiveHint")}</p> : null}
            {result.azureMs ? <p className="muted">{t("fieldAzureMs")} {result.azureMs} ms</p> : null}
          </div>
        )}
        <FieldPulse
          imuSeries={pulse.imu}
          detSeries={pulse.dets}
          classCounts={pulse.counts}
          overlayMs={overlay.inferMs}
          azureMs={pulse.azureMs}
          burstLeftMs={overlay.burstLeftMs}
        />
        <details className="field-more">
          <summary>{t("fieldMore")}</summary>
          <label className="field-file">
            <span>{t("fieldPickPhoto")}</span>
            <input
              type="file"
              accept="image/*"
              capture="environment"
              disabled={!!busy || !hasGps}
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
            <button className="chip" type="button" disabled={!!busy} onClick={() => clearPass()}>{t("fieldClear")}</button>
          </div>
        </details>
        <p className="muted field-honest">{t("fieldHonest")}</p>
      </div>
    </div>
  );
}
