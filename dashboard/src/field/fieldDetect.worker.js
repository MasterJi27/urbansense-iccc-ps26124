import { InferenceSession, Tensor, env } from "onnxruntime-web";
import { cropBand, decodeYolo, letterbox, mapPerson, mapRdd, mergeDets, remapRoi } from "./yoloDecode.js";

env.wasm.numThreads = 2;
env.wasm.proxy = false;
env.wasm.wasmPaths = "/ort/";
if (env.webgpu) env.webgpu.powerPreference = "high-performance";

let rddSess = null;
let personSess = null;
let backend = "wasm";
let manifest = { rdd: { imgsz: 640 }, person: { enabled: false, imgsz: 320 } };
let ready = false;
let tick = 0;
const ROAD_Y0 = 0.32;

async function openSession(url) {
  try {
    const gpu = await Promise.race([
      InferenceSession.create(url, { executionProviders: ["webgpu"] }),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error("webgpu-timeout")), 4000);
      }),
    ]);
    backend = "webgpu";
    return gpu;
  } catch {
    backend = "wasm";
    return InferenceSession.create(url, { executionProviders: ["wasm"] });
  }
}

async function boot() {
  try {
    manifest = await fetch("/weights/manifest.json", { cache: "no-store" }).then((r) => r.json());
  } catch {
    manifest = { rdd: { file: "rdd_web.onnx", imgsz: 640 }, person: { enabled: false } };
  }
  const rddFile = manifest.rdd?.file || "rdd_web.onnx";
  rddSess = await openSession(`/weights/${rddFile}`);
  if (manifest.person?.enabled && manifest.person.file) {
    try {
      personSess = await InferenceSession.create(`/weights/${manifest.person.file}`, {
        executionProviders: [backend === "webgpu" ? "webgpu" : "wasm"],
      });
    } catch {
      try {
        personSess = await InferenceSession.create(`/weights/${manifest.person.file}`, { executionProviders: ["wasm"] });
      } catch {
        personSess = null;
      }
    }
  }
  ready = true;
  self.postMessage({
    type: "ready",
    rddImgsz: manifest.rdd?.imgsz || 640,
    person: Boolean(personSess),
    backend,
  });
}

function imageDataFromBitmap(bitmap, maxEdge) {
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();
  return ctx.getImageData(0, 0, w, h);
}

async function runSession(sess, imageData, imgsz) {
  const boxed = letterbox(imageData, imgsz);
  const input = sess.inputNames[0];
  const tensor = new Tensor("float32", boxed.tensor, [1, 3, imgsz, imgsz]);
  const out = await sess.run({ [input]: tensor });
  const first = out[sess.outputNames[0]];
  const dims = first.dims;
  const data = first.data;
  if (dims.length === 3) {
    const rows = dims[1];
    const cols = dims[2];
    const table = [];
    const channelsFirst = rows < cols;
    if (channelsFirst) {
      for (let c = 0; c < cols; c += 1) {
        const row = [];
        for (let r = 0; r < rows; r += 1) row.push(data[r * cols + c]);
        table.push(row);
      }
    } else {
      for (let r = 0; r < rows; r += 1) {
        const row = [];
        for (let c = 0; c < cols; c += 1) row.push(data[r * cols + c]);
        table.push(row);
      }
    }
    return { table, meta: boxed };
  }
  return { table: [], meta: boxed };
}

function decodeRdd(raw) {
  return decodeYolo(raw.table, raw.meta, {
    conf: 0.22,
    classMap: (idx) => mapRdd(idx),
  });
}

self.onmessage = async (ev) => {
  const msg = ev.data || {};
  if (msg.type === "init") {
    try {
      await boot();
    } catch (err) {
      self.postMessage({ type: "error", message: String(err && err.message ? err.message : err) });
    }
    return;
  }
  if (msg.type !== "frame" || !ready || !rddSess) return;
  const t0 = performance.now();
  try {
    const imageData = imageDataFromBitmap(msg.bitmap, 960);
    const rddImgsz = manifest.rdd?.imgsz || 640;
    const road = cropBand(imageData, ROAD_Y0);
    const roadRaw = await runSession(rddSess, road, rddImgsz);
    const roadDets = remapRoi(decodeRdd(roadRaw), ROAD_Y0);
    let detections = roadDets;
    tick += 1;
    const fullEvery = backend === "webgpu" ? 2 : 4;
    if (tick % fullEvery === 1) {
      const fullRaw = await runSession(rddSess, imageData, rddImgsz);
      detections = mergeDets([roadDets, decodeRdd(fullRaw)]);
    }
    let people = [];
    if (personSess && tick % 2 === 0) {
      const personImgsz = manifest.person?.imgsz || 320;
      const ped = await runSession(personSess, imageData, personImgsz);
      people = decodeYolo(ped.table, ped.meta, {
        conf: 0.4,
        classFilter: 0,
        classMap: (idx) => mapPerson(idx),
      });
    }
    self.postMessage({
      type: "dets",
      detections,
      people,
      personCount: people.length,
      backend,
      infer_ms: Math.round(performance.now() - t0),
    });
  } catch (err) {
    self.postMessage({ type: "error", message: String(err && err.message ? err.message : err) });
  }
};
