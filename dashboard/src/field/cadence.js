export const CADENCE_IDS = ["manual", "detect", "s15", "s5", "s3", "track1s"];

const SPECS = {
  manual: { send: false, overlay: true, gapMs: Number.POSITIVE_INFINITY, burstMs: 0, edgeOnly: false },
  detect: { send: true, overlay: true, gapMs: 3500, burstMs: 0, edgeOnly: true },
  s15: { send: true, overlay: true, gapMs: 15000, burstMs: 0, edgeOnly: false },
  s5: { send: true, overlay: true, gapMs: 5000, burstMs: 0, edgeOnly: false },
  s3: { send: true, overlay: true, gapMs: 3000, burstMs: 0, edgeOnly: false },
  track1s: { send: true, overlay: true, gapMs: 1000, burstMs: 60000, edgeOnly: false },
};

export function cadenceSpec(id) {
  return SPECS[id] || SPECS.detect;
}

export function isPatrol(id) {
  return id !== "manual";
}

export function shouldSend({ cadence, now, lastSend, hasRoad, hadRoad, burstUntil }) {
  const spec = cadenceSpec(cadence);
  if (!spec.send) {
    return { send: false, burstUntil };
  }
  let nextBurst = burstUntil;
  if (hasRoad && spec.burstMs && burstUntil < now) {
    nextBurst = now + spec.burstMs;
  }
  const inBurst = nextBurst > now;
  if (spec.edgeOnly) {
    const rising = hasRoad && !hadRoad;
    return { send: rising && now - lastSend >= spec.gapMs, burstUntil: nextBurst };
  }
  const due = lastSend === 0 || now - lastSend >= spec.gapMs;
  return { send: due && (hasRoad || inBurst), burstUntil: nextBurst };
}
