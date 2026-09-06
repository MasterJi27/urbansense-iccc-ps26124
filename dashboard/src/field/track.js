function iou(a, b) {
  const x1 = Math.max(a[0], b[0]);
  const y1 = Math.max(a[1], b[1]);
  const x2 = Math.min(a[2], b[2]);
  const y2 = Math.min(a[3], b[3]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const aa = Math.max(0, a[2] - a[0]) * Math.max(0, a[3] - a[1]);
  const ba = Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
  return inter / (aa + ba - inter + 1e-9);
}

export function updateTracks(tracks, dets, now = Date.now()) {
  const next = [];
  const used = new Set();
  const sorted = [...(tracks || [])].sort((a, b) => (b.hits || 0) - (a.hits || 0));
  for (const tr of sorted) {
    let best = -1;
    let bestIou = 0.16;
    (dets || []).forEach((d, i) => {
      if (used.has(i)) return;
      if ((d.event_type || d.class_id) !== (tr.event_type || tr.class_id)) return;
      const score = iou(tr.bbox, d.bbox || []);
      if (score > bestIou) {
        bestIou = score;
        best = i;
      }
    });
    if (best < 0) {
      if (now - tr.updated < 900) next.push(tr);
      continue;
    }
    used.add(best);
    const d = dets[best];
    const a = 0.55;
    const bbox = tr.bbox.map((v, i) => v * (1 - a) + d.bbox[i] * a);
    next.push({
      ...d,
      bbox,
      track_id: tr.track_id,
      hits: (tr.hits || 0) + 1,
      updated: now,
    });
  }
  (dets || []).forEach((d, i) => {
    if (used.has(i) || !d.bbox) return;
    next.push({
      ...d,
      track_id: `t${now.toString(36)}${i}`,
      hits: 1,
      updated: now,
    });
  });
  return next.slice(0, 20);
}
