/** Coverage-matrix honesty + India ops helpers. Do not invent neural status. */

export const HONESTY = {
  REAL: "REAL",
  RULE_BASED: "RULE_BASED",
  EXPERIMENTAL: "EXPERIMENTAL",
  SIMULATED: "SIMULATED",
  DISABLED: "DISABLED",
};

const TYPE_DEFAULT = {
  POTHOLE: HONESTY.REAL,
  ROAD_DAMAGE: HONESTY.REAL,
  ROAD_OBSTRUCTION: HONESTY.REAL,
  VEHICLE: HONESTY.REAL,
  MISSING_DIVIDER: HONESTY.RULE_BASED,
  MISSING_ZEBRA: HONESTY.RULE_BASED,
  DAMAGED_SIGN: HONESTY.RULE_BASED,
  TRAFFIC_CONGESTION: HONESTY.RULE_BASED,
  PEDESTRIAN_RISK: HONESTY.RULE_BASED,
  SCHOOL_CROSSING: HONESTY.RULE_BASED,
  HIT_AND_RUN: HONESTY.RULE_BASED,
  RASH_DRIVING: HONESTY.RULE_BASED,
  PEDESTRIAN: HONESTY.RULE_BASED,
  BRIDGE_VIBRATION: HONESTY.RULE_BASED,
  FLYOVER_JOINT: HONESTY.RULE_BASED,
  BRIDGE_ANOMALY: HONESTY.RULE_BASED,
  WATERLOGGING: HONESTY.SIMULATED,
  OTHER: HONESTY.RULE_BASED,
};

export const VRU_TYPES = new Set(["PEDESTRIAN_RISK", "SCHOOL_CROSSING", "PEDESTRIAN"]);
export const MONSOON_TYPES = new Set(["WATERLOGGING"]);
export const PLATE_TYPES = new Set(["HIT_AND_RUN", "RASH_DRIVING", "VEHICLE"]);

const SEV_W = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

export function engineHonesty(ev) {
  const extra = ev?.extra || {};
  if (extra.engine_status && HONESTY[extra.engine_status]) return extra.engine_status;
  if (ev?.event_type === "WATERLOGGING") return HONESTY.SIMULATED;
  if (ev?.event_type === "DAMAGED_SIGN" && extra.signs_enabled === false) return HONESTY.DISABLED;
  return TYPE_DEFAULT[ev?.event_type] || HONESTY.RULE_BASED;
}

export function payloadHonesty(ev) {
  if (!ev) return HONESTY.RULE_BASED;
  const extra = ev.extra || {};
  const raw = extra.ai_status || extra.plate_ai_status || ev.ai_status;
  if (raw && HONESTY[raw]) {
    if (ev.event_type === "WATERLOGGING") return HONESTY.SIMULATED;
    if (ev.event_type === "DAMAGED_SIGN" && extra.signs_enabled === false) return HONESTY.DISABLED;
    return raw;
  }
  if (extra.payload_kind === "SEED" || ev.simulated) return HONESTY.SIMULATED;
  return engineHonesty(ev);
}

/** Jury-facing: seed payload ≠ engine capability. ROAD_DAMAGE seed is SEED, engine is REAL. */
export function dualHonesty(ev) {
  const payload = payloadHonesty(ev);
  const engine = engineHonesty(ev);
  const seed = ev?.extra?.payload_kind === "SEED" || (Boolean(ev?.simulated) && payload === HONESTY.SIMULATED);
  const payloadLabel = seed ? "SEED" : payload;
  return {
    payload,
    engine,
    payloadLabel,
    seed,
    differ: payload !== engine || seed,
    title: seed
      ? `Seed/demo payload. Engine for ${ev?.event_type || "this type"} is ${engine}.`
      : `${payload} payload • ${engine} engine`,
  };
}

export function resolveHonesty(ev) {
  return payloadHonesty(ev);
}

export function honestyClass(status) {
  if (status === HONESTY.REAL) return "real";
  if (status === HONESTY.RULE_BASED) return "rule";
  if (status === HONESTY.SIMULATED || status === HONESTY.EXPERIMENTAL) return "sim";
  if (status === HONESTY.DISABLED) return "off";
  return "info";
}

export function isVru(ev) {
  return VRU_TYPES.has(ev?.event_type);
}

export function isMonsoon(ev) {
  return MONSOON_TYPES.has(ev?.event_type);
}

export function uniqueSources(ev) {
  const obs = ev?.observations || [];
  const ids = new Set(obs.map((o) => o.source_id).filter(Boolean));
  if (ids.size) return [...ids];
  if (ev?.source_id) return [ev.source_id];
  return [];
}

export function patrolLabel(ev) {
  const extra = ev?.extra || {};
  const state = extra.patrol_state || (repeatConfirm(ev).sources >= 2 ? "FLEET_CONFIRMED" : "FIRST_SIGHTING");
  if (state === "FLEET_CONFIRMED") return "2nd bus confirmed";
  return "First sighting — waiting for another bus";
}

export function repeatConfirm(ev) {
  const buses = uniqueSources(ev);
  const obs = ev?.observation_count ?? buses.length;
  const sources = ev?.source_count ?? buses.length;
  const confirmed = obs >= 2 || sources >= 2 || buses.length >= 2;
  return { confirmed, buses, obs, sources };
}

export function repairPriority({ severity, observationCount, sourceCount, trafficExposure, pedestrianExposure }) {
  const sev = SEV_W[severity] || 1;
  const repeat = Math.min(Number(observationCount) || 1, 8);
  const sources = Math.min(Number(sourceCount) || 1, 5);
  const traffic = Number(trafficExposure);
  const ped = Number(pedestrianExposure);
  const routeImp = Number.isFinite(traffic) ? Math.min(2, Math.max(0.5, traffic / 40)) : 1;
  const vruImp = Number.isFinite(ped) ? Math.min(1.5, Math.max(0, ped / 80)) : 0;
  const score = Math.round(sev * 16 + repeat * 7 + sources * 5 + (routeImp - 1) * 18 + vruImp * 12);
  return Math.max(0, Math.min(100, score));
}

export function priorityBand(score) {
  if (score >= 72) return "CRITICAL";
  if (score >= 52) return "HIGH";
  if (score >= 32) return "MEDIUM";
  return "LOW";
}

/** Coarse Delhi ICCC zone from lat/lon — RULE_BASED, not official ward GIS. */
export function delhiZone(lat, lon) {
  if (lat == null || lon == null || !Number.isFinite(Number(lat))) return { zone: "—", ward: "—" };
  const y = Number(lat);
  const x = Number(lon);
  let zone = "Central";
  if (y >= 28.68) zone = "North";
  else if (y <= 28.54) zone = "South";
  else if (x >= 77.26) zone = "East";
  else if (x <= 77.16) zone = "West";
  const wardN = 12 + (Math.abs(Math.round((y * 1000 + x * 100) % 19)) % 18);
  return { zone, ward: `Ward ${wardN}` };
}

export function maskPlate(text) {
  if (!text) return "";
  const raw = String(text).replace(/\s+/g, "");
  if (raw.length <= 4) return "••••";
  return `${raw.slice(0, 4)}••••`;
}

export function canRevealPlate(role) {
  const r = String(role || "").toUpperCase();
  return r === "ADMIN" || r === "SUPER_ADMIN" || r === "INSPECTOR";
}

export function edgeModeFromProcessing(mode) {
  const m = String(mode || "").toUpperCase();
  if (m === "EDGE_AI") return { tier: "HIGH", label: "HIGH — selective neural", models: "RDD + vehicles/ByteTrack + ANPR on trigger stills" };
  if (m === "LIGHTWEIGHT_EDGE_AI") return { tier: "MED", label: "MED — lightweight", models: "RDD stills only; skip ANPR/track unless incident trigger" };
  if (m === "CAPTURE_AND_SENSOR" || m === "CLOUD_ASSISTED") return { tier: "LOW", label: "LOW — IMU + GPS", models: "Phone trigger ~1KB JSON; no on-device YOLO" };
  return { tier: "LOW", label: "LOW — capture", models: "Sensor heartbeat; backend inference on demand" };
}

export function readFlag(key, fallback = false) {
  try {
    const v = localStorage.getItem(key);
    if (v == null) return fallback;
    return v === "1" || v === "true";
  } catch {
    return fallback;
  }
}

export function writeFlag(key, value) {
  try { localStorage.setItem(key, value ? "1" : "0"); } catch { /* ignore */ }
}
