import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { cadenceSpec, isPatrol, shouldSend } from "./cadence.js";
import { updateTracks } from "./track.js";

const CLOUD_TICK_MS = 900;

export function useFieldOverlay({
  authed,
  cadence,
  patrol,
  videoRef,
  blobFromVideo,
  postStill,
  setBoxes,
  setResult,
  onError,
  onPulse,
}) {
  const [mode, setMode] = useState("idle");
  const [personCount, setPersonCount] = useState(0);
  const [overlayFps, setOverlayFps] = useState(0);
  const [backend, setBackend] = useState("wasm");
  const [inferMs, setInferMs] = useState(0);
  const [burstLeftMs, setBurstLeftMs] = useState(0);
  const blobRef = useRef(blobFromVideo);
  const postRef = useRef(postStill);
  const boxesRef = useRef(setBoxes);
  const resultRef = useRef(setResult);
  const errorRef = useRef(onError);
  const pulseRef = useRef(onPulse);
  const cadenceRef = useRef(cadence);
  const lastIngest = useRef(0);
  const lastBoxesRef = useRef([]);
  const lastPeopleRef = useRef([]);
  const tracksRef = useRef([]);
  const fpsTimes = useRef([]);
  const fpsRef = useRef(0);
  const backendRef = useRef("wasm");
  const inferMsRef = useRef(0);
  const hadRoadRef = useRef(false);
  const burstUntilRef = useRef(0);
  const ingestingRef = useRef(false);

  blobRef.current = blobFromVideo;
  postRef.current = postStill;
  boxesRef.current = setBoxes;
  resultRef.current = setResult;
  errorRef.current = onError;
  pulseRef.current = onPulse;
  cadenceRef.current = cadence || (patrol === false ? "manual" : "detect");

  function noteIngest(ingested, found, prefix) {
    const ev = ingested.event || {};
    const extra = ev.extra || {};
    resultRef.current({
      path: ingested.observation?.extra?.ai_status || "REAL",
      title: ev.public_code,
      type: ev.event_type,
      created: ingested.created_event,
      patrol: extra.patrol_state,
      eventId: ev.id,
      live: Boolean(extra.live_photo_url),
      azureMs: extra.azure_still_ms || extra.rdd_infer_ms,
      note: `${prefix} · ${found[0]?.klass || ev.event_type}${extra.azure_still_ms ? ` · Azure ${extra.azure_still_ms} ms` : ""}`,
      raw: ingested,
    });
  }

  function fireIngest(found, jpegPromise, prefix) {
    if (ingestingRef.current) return;
    ingestingRef.current = true;
    lastIngest.current = Date.now();
    jpegPromise()
      .then((jpeg) => postRef.current(jpeg))
      .then((ingested) => noteIngest(ingested, found, prefix))
      .catch((ex) => {
        const msg = ex.message || "Still ingest failed";
        if (msg === "Allow location") return;
        if (typeof errorRef.current === "function") errorRef.current(msg);
      })
      .finally(() => {
        ingestingRef.current = false;
      });
  }

  function considerIngest(roads, jpegPromise, prefix) {
    const now = Date.now();
    const hasRoad = roads.length > 0;
    const decision = shouldSend({
      cadence: cadenceRef.current,
      now,
      lastSend: lastIngest.current,
      hasRoad,
      hadRoad: hadRoadRef.current,
      burstUntil: burstUntilRef.current,
    });
    burstUntilRef.current = decision.burstUntil;
    setBurstLeftMs(Math.max(0, decision.burstUntil - now));
    hadRoadRef.current = hasRoad;
    if (decision.send) fireIngest(roads, jpegPromise, prefix);
  }

  function paintTracked(rdd, people) {
    const tracked = updateTracks(tracksRef.current, [...(rdd || []), ...(people || [])]);
    tracksRef.current = tracked;
    const roads = tracked.filter((d) => d.event_type !== "PEDESTRIAN");
    const peds = tracked.filter((d) => d.event_type === "PEDESTRIAN");
    lastBoxesRef.current = roads;
    lastPeopleRef.current = peds;
    setPersonCount(peds.length);
    boxesRef.current(tracked);
    if (typeof pulseRef.current === "function") {
      pulseRef.current({ roads, people: peds, inferMs: inferMsRef.current });
    }
    return roads;
  }

  const overlayOn = authed && cadenceSpec(cadence || (patrol === false ? "manual" : "detect")).overlay;

  useEffect(() => {
    if (!overlayOn) {
      setMode("idle");
      tracksRef.current = [];
      lastBoxesRef.current = [];
      lastPeopleRef.current = [];
      boxesRef.current([]);
      setPersonCount(0);
      setBurstLeftMs(0);
      return undefined;
    }
    let dead = false;
    let ready = false;
    let worker;
    try {
      worker = new Worker(new URL("./fieldDetect.worker.js", import.meta.url), { type: "module" });
    } catch {
      setMode("cloud");
      return undefined;
    }
    setMode("loading");
    let raf = 0;
    let inFlight = false;
    const bootTimer = window.setTimeout(() => {
      if (dead || ready) return;
      setMode("cloud");
      worker.terminate();
    }, 20000);

    worker.onmessage = (ev) => {
      const msg = ev.data || {};
      if (msg.type === "ready") {
        ready = true;
        window.clearTimeout(bootTimer);
        const ep = msg.backend === "webgpu" ? "webgpu" : "wasm";
        backendRef.current = ep;
        setBackend(ep);
        if (!dead) setMode("ondevice");
        return;
      }
      if (msg.type === "error") {
        inFlight = false;
        if (!ready) {
          setMode("cloud");
          worker.terminate();
        }
        return;
      }
      if (msg.type !== "dets" || dead) return;
      inFlight = false;
      const rdd = msg.detections || [];
      const people = msg.people || [];
      if (typeof msg.infer_ms === "number") {
        inferMsRef.current = msg.infer_ms;
        setInferMs(msg.infer_ms);
      }
      if (msg.backend) {
        const ep = msg.backend === "webgpu" ? "webgpu" : "wasm";
        backendRef.current = ep;
        setBackend(ep);
      }
      const now = performance.now();
      fpsTimes.current.push(now);
      fpsTimes.current = fpsTimes.current.filter((t) => now - t < 1000);
      setOverlayFps(fpsTimes.current.length);
      fpsRef.current = fpsTimes.current.length;
      const roads = paintTracked(rdd, people);
      considerIngest(roads, () => blobRef.current(), "AUTO · Azure ticket + clip");
    };

    worker.postMessage({ type: "init" });
    const loop = () => {
      if (dead) return;
      raf = window.requestAnimationFrame(loop);
      if (!ready || inFlight) return;
      const video = videoRef.current;
      if (!video || !video.videoWidth || typeof createImageBitmap !== "function") return;
      inFlight = true;
      createImageBitmap(video)
        .then((bitmap) => {
          if (dead) {
            bitmap.close();
            inFlight = false;
            return;
          }
          worker.postMessage({ type: "frame", bitmap }, [bitmap]);
        })
        .catch(() => {
          inFlight = false;
        });
    };
    raf = window.requestAnimationFrame(loop);

    return () => {
      tracksRef.current = [];
      lastBoxesRef.current = [];
      lastPeopleRef.current = [];
      window.clearTimeout(bootTimer);
      window.cancelAnimationFrame(raf);
      worker.terminate();
    };
  }, [overlayOn, videoRef]);

  useEffect(() => {
    if (!overlayOn || mode !== "cloud") return undefined;
    let dead = false;
    let probing = false;
    const tick = window.setInterval(async () => {
      if (dead || probing) return;
      probing = true;
      try {
        const jpeg = await blobRef.current();
        const fd = new FormData();
        fd.append("file", jpeg, "field-probe.jpg");
        const probed = await api("/ingest/phone/probe", { method: "POST", body: fd });
        if (dead) return;
        const found = probed.detections || [];
        const roads = paintTracked(found, []);
        considerIngest(roads, async () => jpeg, "AUTO · cloud preview");
      } catch {
        /* lens not ready */
      } finally {
        probing = false;
      }
    }, CLOUD_TICK_MS);
    return () => {
      dead = true;
      window.clearInterval(tick);
    };
  }, [overlayOn, mode]);

  useEffect(() => {
    if (!isPatrol(cadence || (patrol === false ? "manual" : "detect"))) {
      burstUntilRef.current = 0;
      hadRoadRef.current = false;
      setBurstLeftMs(0);
    }
  }, [cadence]);

  return {
    mode,
    personCount,
    overlayFps,
    backend,
    inferMs,
    burstLeftMs,
    lastBoxes: lastBoxesRef,
    lastPeople: lastPeopleRef,
    fpsRef,
    backendRef,
    inferMsRef,
  };
}
