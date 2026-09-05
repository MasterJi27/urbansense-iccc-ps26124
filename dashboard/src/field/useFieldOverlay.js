import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { updateTracks } from "./track.js";

const INGEST_GAP_MS = 800;
const CLOUD_TICK_MS = 900;

export function useFieldOverlay({
  authed,
  patrol,
  videoRef,
  blobFromVideo,
  postStill,
  setBoxes,
  setResult,
  onError,
}) {
  const [mode, setMode] = useState("idle");
  const [personCount, setPersonCount] = useState(0);
  const [overlayFps, setOverlayFps] = useState(0);
  const [backend, setBackend] = useState("wasm");
  const [inferMs, setInferMs] = useState(0);
  const blobRef = useRef(blobFromVideo);
  const postRef = useRef(postStill);
  const boxesRef = useRef(setBoxes);
  const resultRef = useRef(setResult);
  const errorRef = useRef(onError);
  const lastIngest = useRef(0);
  const lastBoxesRef = useRef([]);
  const lastPeopleRef = useRef([]);
  const tracksRef = useRef([]);
  const fpsTimes = useRef([]);
  const fpsRef = useRef(0);
  const backendRef = useRef("wasm");
  const inferMsRef = useRef(0);

  blobRef.current = blobFromVideo;
  postRef.current = postStill;
  boxesRef.current = setBoxes;
  resultRef.current = setResult;
  errorRef.current = onError;

  function noteIngest(ingested, found, prefix) {
    const ev = ingested.event || {};
    resultRef.current({
      path: ingested.observation?.extra?.ai_status || "REAL",
      title: ev.public_code,
      type: ev.event_type,
      created: ingested.created_event,
      patrol: ev.extra?.patrol_state,
      eventId: ev.id,
      note: `${prefix} · ${found[0]?.klass || ev.event_type}`,
      raw: ingested,
    });
  }

  function maybeIngest(found, jpegPromise, prefix) {
    if (!found.length) return;
    if (Date.now() - lastIngest.current <= INGEST_GAP_MS) return;
    lastIngest.current = Date.now();
    jpegPromise()
      .then((jpeg) => postRef.current(jpeg))
      .then((ingested) => noteIngest(ingested, found, prefix))
      .catch((ex) => {
        if (typeof errorRef.current === "function") errorRef.current(ex.message || "Still ingest failed");
      });
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
    return roads;
  }

  useEffect(() => {
    if (!authed || !patrol) {
      setMode("idle");
      tracksRef.current = [];
      lastBoxesRef.current = [];
      lastPeopleRef.current = [];
      boxesRef.current([]);
      setPersonCount(0);
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
      paintTracked(rdd, people);
      maybeIngest(rdd, () => blobRef.current(), "Auto still · Azure RDD confirm");
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
  }, [authed, patrol, videoRef]);

  useEffect(() => {
    if (!authed || !patrol || mode !== "cloud") return undefined;
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
        paintTracked(found, []);
        maybeIngest(found, async () => jpeg, "CLOUD PREVIEW · Azure RDD");
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
  }, [authed, patrol, mode]);

  return {
    mode,
    personCount,
    overlayFps,
    backend,
    inferMs,
    lastBoxes: lastBoxesRef,
    lastPeople: lastPeopleRef,
    fpsRef,
    backendRef,
    inferMsRef,
  };
}
