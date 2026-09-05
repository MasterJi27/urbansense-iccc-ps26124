export const RDD_CLASSES = [
  { id: "D00", name: "Longitudinal crack", event_type: "ROAD_DAMAGE" },
  { id: "D10", name: "Transverse crack", event_type: "ROAD_DAMAGE" },
  { id: "D20", name: "Alligator crack", event_type: "ROAD_DAMAGE" },
  { id: "D40", name: "Pothole", event_type: "POTHOLE" },
];

export function letterbox(imageData, imgsz) {
  const srcW = imageData.width;
  const srcH = imageData.height;
  const scale = Math.min(imgsz / srcW, imgsz / srcH);
  const nw = Math.max(1, Math.round(srcW * scale));
  const nh = Math.max(1, Math.round(srcH * scale));
  const padX = Math.floor((imgsz - nw) / 2);
  const padY = Math.floor((imgsz - nh) / 2);
  const canvas = new OffscreenCanvas(imgsz, imgsz);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "rgb(114,114,114)";
  ctx.fillRect(0, 0, imgsz, imgsz);
  const tmp = new OffscreenCanvas(srcW, srcH);
  tmp.getContext("2d").putImageData(imageData, 0, 0);
  ctx.drawImage(tmp, 0, 0, srcW, srcH, padX, padY, nw, nh);
  const boxed = ctx.getImageData(0, 0, imgsz, imgsz);
  const tensor = new Float32Array(3 * imgsz * imgsz);
  const { data } = boxed;
  const plane = imgsz * imgsz;
  for (let i = 0; i < plane; i += 1) {
    tensor[i] = data[i * 4] / 255;
    tensor[plane + i] = data[i * 4 + 1] / 255;
    tensor[plane * 2 + i] = data[i * 4 + 2] / 255;
  }
  return { tensor, scale, padX, padY, srcW, srcH, imgsz };
}

function nms(boxes, scores, iouTh = 0.45) {
  const order = scores.map((_, i) => i).sort((a, b) => scores[b] - scores[a]);
  const keep = [];
  const areas = boxes.map(([x1, y1, x2, y2]) => Math.max(0, x2 - x1) * Math.max(0, y2 - y1));
  while (order.length) {
    const i = order.shift();
    keep.push(i);
    const rest = [];
    for (const j of order) {
      const xx1 = Math.max(boxes[i][0], boxes[j][0]);
      const yy1 = Math.max(boxes[i][1], boxes[j][1]);
      const xx2 = Math.min(boxes[i][2], boxes[j][2]);
      const yy2 = Math.min(boxes[i][3], boxes[j][3]);
      const inter = Math.max(0, xx2 - xx1) * Math.max(0, yy2 - yy1);
      const iou = inter / (areas[i] + areas[j] - inter + 1e-9);
      if (iou < iouTh) rest.push(j);
    }
    order.length = 0;
    order.push(...rest);
  }
  return keep;
}

export function decodeYolo(raw, meta, { conf = 0.22, classFilter = null, classMap = null } = {}) {
  const { scale, padX, padY, srcW, srcH } = meta;
  let table = raw;
  if (!Array.isArray(table) || !table.length) return [];
  if (!Array.isArray(table[0])) table = [table];
  if (table[0].length === 6) {
    return decodePacked(table, meta, { conf, classFilter, classMap });
  }
  const boxes = [];
  const scores = [];
  const ids = [];
  for (const row of table) {
    if (!row || row.length < 6) continue;
    const [x, y, w, h] = row;
    const cls = row.slice(4);
    let best = 0;
    let bestI = 0;
    for (let i = 0; i < cls.length; i += 1) {
      if (cls[i] > best) {
        best = cls[i];
        bestI = i;
      }
    }
    if (best < conf) continue;
    if (classFilter != null && bestI !== classFilter) continue;
    boxes.push([x - w / 2, y - h / 2, x + w / 2, y + h / 2]);
    scores.push(best);
    ids.push(bestI);
  }
  const keep = nms(boxes, scores).slice(0, 20);
  const dets = [];
  for (const i of keep) {
    const [x1, y1, x2, y2] = boxes[i];
    const nx1 = Math.max(0, Math.min(1, ((x1 - padX) / scale) / srcW));
    const ny1 = Math.max(0, Math.min(1, ((y1 - padY) / scale) / srcH));
    const nx2 = Math.max(0, Math.min(1, ((x2 - padX) / scale) / srcW));
    const ny2 = Math.max(0, Math.min(1, ((y2 - padY) / scale) / srcH));
    if (nx2 - nx1 <= 0 || ny2 - ny1 <= 0) continue;
    const mapped = classMap ? classMap(ids[i], scores[i]) : null;
    if (!mapped) continue;
    dets.push({
      ...mapped,
      confidence: Math.round(scores[i] * 10000) / 10000,
      bbox: [
        Math.round(nx1 * 10000) / 10000,
        Math.round(ny1 * 10000) / 10000,
        Math.round(nx2 * 10000) / 10000,
        Math.round(ny2 * 10000) / 10000,
      ],
    });
  }
  dets.sort((a, b) => b.confidence - a.confidence);
  return dets;
}

function toNormBox(x1, y1, x2, y2, meta) {
  const { scale, padX, padY, srcW, srcH } = meta;
  const nx1 = Math.max(0, Math.min(1, ((x1 - padX) / scale) / srcW));
  const ny1 = Math.max(0, Math.min(1, ((y1 - padY) / scale) / srcH));
  const nx2 = Math.max(0, Math.min(1, ((x2 - padX) / scale) / srcW));
  const ny2 = Math.max(0, Math.min(1, ((y2 - padY) / scale) / srcH));
  if (nx2 - nx1 <= 0 || ny2 - ny1 <= 0) return null;
  return [
    Math.round(nx1 * 10000) / 10000,
    Math.round(ny1 * 10000) / 10000,
    Math.round(nx2 * 10000) / 10000,
    Math.round(ny2 * 10000) / 10000,
  ];
}

function decodePacked(table, meta, { conf, classFilter, classMap }) {
  const dets = [];
  for (const row of table) {
    const score = row[4];
    const cls = Math.round(row[5]);
    if (score < conf) continue;
    if (classFilter != null && cls !== classFilter) continue;
    const mapped = classMap ? classMap(cls, score) : null;
    if (!mapped) continue;
    const bbox = toNormBox(row[0], row[1], row[2], row[3], meta);
    if (!bbox) continue;
    dets.push({ ...mapped, confidence: Math.round(score * 10000) / 10000, bbox });
  }
  dets.sort((a, b) => b.confidence - a.confidence);
  return dets.slice(0, 20);
}

export function cropBand(imageData, y0frac) {
  const y0 = Math.max(0, Math.min(imageData.height - 1, Math.floor(imageData.height * y0frac)));
  const h = Math.max(1, imageData.height - y0);
  const src = new OffscreenCanvas(imageData.width, imageData.height);
  src.getContext("2d").putImageData(imageData, 0, 0);
  const dst = new OffscreenCanvas(imageData.width, h);
  dst.getContext("2d").drawImage(src, 0, y0, imageData.width, h, 0, 0, imageData.width, h);
  return dst.getContext("2d").getImageData(0, 0, imageData.width, h);
}

export function remapRoi(dets, y0frac) {
  const span = Math.max(0.05, 1 - y0frac);
  return (dets || []).map((d) => {
    const box = d.bbox || [];
    if (box.length < 4) return d;
    return {
      ...d,
      bbox: [box[0], y0frac + box[1] * span, box[2], y0frac + box[3] * span],
    };
  });
}

export function mergeDets(lists, iouTh = 0.45) {
  const dets = (lists || []).flat().filter((d) => d && Array.isArray(d.bbox) && d.bbox.length >= 4);
  dets.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
  if (dets.length <= 1) return dets.slice(0, 20);
  const boxes = dets.map((d) => d.bbox);
  const scores = dets.map((d) => d.confidence || 0);
  return nms(boxes, scores, iouTh).map((i) => dets[i]).slice(0, 20);
}

export function mapRdd(idx) {
  const meta = RDD_CLASSES[idx];
  if (!meta) return null;
  return { klass: meta.name, class_id: meta.id, event_type: meta.event_type };
}

export function mapPerson(idx) {
  if (idx !== 0) return null;
  return { klass: "person", class_id: "person", event_type: "PEDESTRIAN" };
}
