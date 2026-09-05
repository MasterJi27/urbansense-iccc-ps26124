"""
UrbanSense Structural Pulse — Continuous bridge-health SCREENING (never collapse prediction).

See docs/STRUCTURAL_PULSE.md for correct jury framing.

Concept: Buses already crossing bridges 100s/day become temporary sensing nodes.
Phone accel (50Hz) + GPS 1Hz on bridge geofence → RMS/peak/crest + FFT f_dom →
per-bridge EMA baseline (0.92/0.08) → persistent drift across multiple buses
→ flag for engineering INSPECTION. RULE_BASED screening layer, not certified SHM.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy.orm import Session

from app.geo import haversine_m
from app.models.asset import Asset, AssetType
from app.models.event import EventType, Severity, SourceType
from app.models.ops import NotificationLog
from app.models.shm import BridgeHealthLog
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.schemas.common import ObservationIn
from app.services.observations import ingest_observation

logger = logging.getLogger(__name__)


class BridgeIngestResult(TypedDict, total=False):
    matched: bool
    reason: str
    features: dict
    bridge_code: str
    bridge_name: str
    event_type: str
    severity: str
    confidence: float
    observation_id: str
    event_id: str
    event_code: str
    created: bool
    baseline_rms: float | None
    baseline_freq: float | None
    health_score: float
    predicted_days: int | None
    wo_code: str | None

BRIDGE_GEOFENCE_M = 70
ANOMALY_RMS_RATIO = 1.6
ANOMALY_PEAK_RATIO = 1.8
ANOMALY_FREQ_SHIFT_HZ = 0.9
RMS_HIGH_G = 0.45


@dataclass
class AccelSample:
    t: float; ax: float; ay: float; az: float

@dataclass
class BridgeFeatures:
    rms: float
    peak: float
    crest: float
    dominant_freq: float
    freq_power: float
    count: int
    duration_s: float
    speed_kmh: float | None

def _mag(a: AccelSample) -> float:
    return math.sqrt(a.ax*a.ax + a.ay*a.ay + a.az*a.az)

def _dominant_freq(centered: list[float], dt: float) -> tuple[float,float]:
    # simple FFT — robust to 0, no numpy hard dep fallback via zero-crossing
    try:
        import numpy as np
        if len(centered) < 16 or dt <= 0: return 0.0, 0.0
        n = len(centered)
        # Hanning window
        w = np.hanning(n)
        y = np.array(centered) * w
        spectrum = np.abs(np.fft.rfft(y))
        freqs = np.fft.rfftfreq(n, d=dt)
        # ignore DC <0.8Hz (bus body)
        mask = freqs >= 0.8
        if not mask.any(): return 0.0, 0.0
        idx = int(np.argmax(spectrum[mask]))
        # map back
        freqs_m = freqs[mask]
        spec_m = spectrum[mask]
        return float(freqs_m[idx]), float(spec_m[idx] / (spec_m.sum()+1e-9))
    except Exception:
        # zero-crossing fallback ~ approx freq
        try:
            crossings = sum(1 for i in range(1,len(centered)) if centered[i-1]<=0 < centered[i])
            dur = len(centered)*dt
            return (crossings / max(0.5,dur))/2 if dur>0 else 0.0, 0.0
        except: return 0.0,0.0

def extract_features(samples: list[AccelSample], speed_kmh: float | None) -> BridgeFeatures:
    if not samples:
        return BridgeFeatures(rms=0, peak=0, crest=0, dominant_freq=0, freq_power=0, count=0, duration_s=0, speed_kmh=speed_kmh)
    mags = [_mag(s) for s in samples]
    mean = sum(mags)/len(mags)
    centered = [abs(m - mean) for m in mags]
    rms = math.sqrt(sum(c*c for c in centered)/len(centered)) if centered else 0
    peak = max(centered) if centered else 0
    crest = (peak / rms) if rms > 1e-6 else 0
    dur = samples[-1].t - samples[0].t if len(samples) > 1 else 0
    dt = dur / max(1, len(samples)-1) if len(samples)>1 else 0.02
    dom_f, pwr = _dominant_freq(centered, dt)
    return BridgeFeatures(rms=rms, peak=peak, crest=crest, dominant_freq=dom_f, freq_power=pwr, count=len(samples), duration_s=dur, speed_kmh=speed_kmh)

def find_bridge(db: Session, lat: float, lon: float) -> Asset | None:
    for a in db.query(Asset).filter(Asset.asset_type.in_([AssetType.BRIDGE, AssetType.FLYOVER])).all():
        if haversine_m(lat, lon, a.latitude, a.longitude) <= BRIDGE_GEOFENCE_M:
            return a
    return None

def _severity(feat: BridgeFeatures, bridge: Asset) -> Severity:
    # temp compensation placeholder — if temp logged, high temp softens threshold 3%
    if feat.rms >= 0.55 or feat.peak >= 1.2:
        return Severity.CRITICAL
    # freq shift check
    if bridge.shm_baseline_freq and feat.dominant_freq>0:
        shift = abs(feat.dominant_freq - bridge.shm_baseline_freq)
        if shift >= ANOMALY_FREQ_SHIFT_HZ and feat.freq_power>0.18:
            return Severity.HIGH
    if bridge.shm_baseline_rms and bridge.shm_baseline_rms>0:
        ratio = feat.rms / bridge.shm_baseline_rms
        if ratio >= 2.0: return Severity.CRITICAL
        if ratio >= ANOMALY_RMS_RATIO: return Severity.HIGH
    if feat.rms >= RMS_HIGH_G: return Severity.HIGH
    if feat.peak >= 0.8: return Severity.MEDIUM
    return Severity.LOW

def classify_vibration(feat: BridgeFeatures, bridge: Asset) -> tuple[EventType, Severity, float, str]:
    sev = _severity(feat, bridge)
    etype = EventType.FLYOVER_JOINT if feat.crest >= 4.5 and feat.peak >= 0.7 else (
        EventType.BRIDGE_ANOMALY if sev in (Severity.HIGH, Severity.CRITICAL) else EventType.BRIDGE_VIBRATION)
    if bridge.shm_baseline_rms and bridge.shm_baseline_rms>0:
        ratio = feat.rms / bridge.shm_baseline_rms
        conf = min(0.92, 0.55 + 0.2*max(0, ratio-1))
        # freq shift boosts confidence
        if bridge.shm_baseline_freq and feat.dominant_freq>0 and abs(feat.dominant_freq-bridge.shm_baseline_freq)>=0.7:
            conf = min(0.94, conf+0.08)
    else:
        conf = min(0.85, 0.5 + feat.rms)
    freq_part = f" f_dom={feat.dominant_freq:.1f}Hz({feat.freq_power:.2f}) baseF={bridge.shm_baseline_freq:.1f}Hz" if bridge.shm_baseline_freq else f" f_dom={feat.dominant_freq:.1f}Hz"
    reason = (
        f"bridge={bridge.code} span~{bridge.span_m or '?'}m; rms={feat.rms:.3f}g peak={feat.peak:.3f}g crest={feat.crest:.1f}{freq_part} "
        f"baseline={bridge.shm_baseline_rms:.3f}g" if bridge.shm_baseline_rms else f"bridge={bridge.code}; rms={feat.rms:.3f}g peak={feat.peak:.3f}g{freq_part} (no baseline)"
        + (f"; n={feat.count} dur={feat.duration_s:.1f}s speed={feat.speed_kmh:.0f}km/h" if feat.speed_kmh else "")
        + f"; geofence {BRIDGE_GEOFENCE_M}m"
    )
    logger.info(
        "classify_vibration bridge=%s etype=%s severity=%s conf=%.2f rms=%.3f peak=%.3f crest=%.1f dom=%.1fHz reason=%s",
        bridge.code,
        etype.value,
        sev.value,
        conf,
        feat.rms,
        feat.peak,
        feat.crest,
        feat.dominant_freq,
        reason,
    )
    return etype, sev, conf, reason

def _predict_days(bridge: Asset, db: Session) -> int | None:
    logs = db.query(BridgeHealthLog).filter(BridgeHealthLog.bridge_id==bridge.id).order_by(BridgeHealthLog.created_at.desc()).limit(14).all()
    if len(logs) < 6: return None
    # linear trend on rms vs time
    try:
        import time
        xs = [l.created_at.timestamp() for l in logs][::-1]
        ys = [l.rms for l in logs][::-1]
        x0 = xs[0]
        xs = [(x-x0)/86400 for x in xs]  # days
        n = len(xs)
        sx=sum(xs); sy=sum(ys); sxx=sum(x*x for x in xs); sxy=sum(x*y for x,y in zip(xs,ys))
        denom = n*sxx - sx*sx
        if abs(denom)<1e-9: return None
        slope = (n*sxy - sx*sy)/denom
        if slope <= 0.008: return None  # not degrading
        # days to reach 0.55g critical from last rms
        last = ys[-1]
        target = 0.55
        days = (target - last)/slope
        if days < 0 or days > 365: return None
        return int(days)
    except: return None

def ingest_bridge_batch(
    db: Session,
    samples: list[AccelSample],
    lat: float, lon: float,
    gps_accuracy: float | None,
    speed_kmh: float | None,
    source_type: SourceType,
    source_id: str,
    sensor_id: str | None = None,
    bus_id: str | None = None,
    route_id: str | None = None,
    simulated: bool = False,
    temp_c: float | None = None,
) -> BridgeIngestResult:
    feat = extract_features(samples, speed_kmh)
    bridge = find_bridge(db, lat, lon)
    if not bridge:
        logger.info("ingest_bridge_batch no bridge within %sm lat=%.5f lon=%.5f rms=%.3f", BRIDGE_GEOFENCE_M, lat, lon, feat.rms)
        return {"matched": False, "reason": f"no bridge within {BRIDGE_GEOFENCE_M}m", "features": feat.__dict__}
    etype, sev, conf, reason = classify_vibration(feat, bridge)
    logger.info(
        "ingest_bridge_batch bridge=%s matched severity=%s conf=%.2f rms=%.3f peak=%.3f reason=%s",
        bridge.code,
        sev.value,
        conf,
        feat.rms,
        feat.peak,
        reason,
    )
    # EMA baselines
    if bridge.shm_baseline_rms is None:
        bridge.shm_baseline_rms = feat.rms
        bridge.shm_baseline_freq = feat.dominant_freq if feat.dominant_freq>0.5 else bridge.shm_baseline_freq
    else:
        bridge.shm_baseline_rms = 0.92*bridge.shm_baseline_rms + 0.08*feat.rms
        if feat.dominant_freq>0.5:
            base_f = bridge.shm_baseline_freq or feat.dominant_freq
            bridge.shm_baseline_freq = 0.94*base_f + 0.06*feat.dominant_freq
    bridge.shm_last_rms = feat.rms
    bridge.shm_last_freq = feat.dominant_freq
    bridge.shm_last_checked = datetime.now(timezone.utc)
    if sev in (Severity.HIGH, Severity.CRITICAL):
        bridge.shm_anomaly_count = (bridge.shm_anomaly_count or 0) + 1
        bridge.health_score = max(0, bridge.health_score - (12 if sev==Severity.CRITICAL else 6))
    else:
        # slow recovery
        bridge.health_score = min(100, bridge.health_score + 0.4)
    # log
    log = BridgeHealthLog(bridge_id=bridge.id, rms=feat.rms, peak=feat.peak, crest=feat.crest, dominant_freq=feat.dominant_freq, speed_kmh=speed_kmh, temp_c=temp_c, source_id=source_id, health_score=bridge.health_score, anomaly=sev.value if sev in (Severity.HIGH,Severity.CRITICAL) else "NO", note=reason[:500])
    db.add(log); db.flush()
    # predictive
    days = _predict_days(bridge, db)
    bridge.predicted_days_to_maintenance = days

    obs_in = ObservationIn(
        event_type=etype, severity=sev,
        latitude=bridge.latitude, longitude=bridge.longitude,
        gps_accuracy=gps_accuracy, timestamp=datetime.now(timezone.utc),
        source_type=source_type, source_id=source_id, sensor_id=sensor_id, bus_id=bus_id, route_id=route_id,
        confidence=conf, simulated=simulated, speed_kmh=speed_kmh,
        extra={"ai_status":"RULE_BASED","derivation":"Structural Pulse screening — repeatable dynamic features (RMS/peak/crest + FFT f_dom) vs per-structure EMA baseline across multiple buses; flag for inspection, not safety judgment","shm_features":feat.__dict__,"shm_reason":reason,"shm_baseline_rms":bridge.shm_baseline_rms,"shm_baseline_freq":bridge.shm_baseline_freq,"shm_bridge_code":bridge.code,"shm_bridge_name":bridge.name,"method":"fleet screening: accel+GFS crowd anomaly","predicted_days":days,"temp_c":temp_c,"screening_layer":"early-warning, not certified inspection"},
    )
    obs, event, created = ingest_observation(db, obs_in)
    # auto work order for CRITICAL + simple in-app notification log
    wo_code = None
    wo_id = None
    if sev == Severity.CRITICAL:
        existing = db.query(WorkOrder).filter(WorkOrder.event_id==event.id).first()
        if not existing:
            wo_code = f"WO-BR-{bridge.code}-{event.public_code[-4:]}"
            wo = WorkOrder(public_code=wo_code, event_id=event.id, asset_id=bridge.id, title=f"Bridge SHM CRITICAL — {bridge.code} {etype.value}", description=f"Auto from crowd vibration: {reason} | predicted {days}d to maintenance" if days else f"Auto from crowd vibration: {reason}", status=WorkOrderStatus.PENDING, qr_payload=f"urbansense://work-order/{wo_code}")
            db.add(wo); db.flush()
            wo_id = wo.id
        else:
            wo_id = existing.id
            wo_code = existing.public_code
        # notification log for CRITICAL (reuse NotificationLog, not just AuditLog)
        notif = NotificationLog(
            title=f"Bridge SHM CRITICAL — {bridge.code}",
            message=f"{etype.value} rms={feat.rms:.3f}g peak={feat.peak:.3f}g at {bridge.name} | {reason[:240]}",
            severity=Severity.CRITICAL.value,
            event_id=event.id,
            work_order_id=wo_id,
            channel="bridge_shm",
        )
        db.add(notif)
        db.flush()
        db.commit()
    return {"matched":True,"bridge_code":bridge.code,"bridge_name":bridge.name,"features":feat.__dict__,"event_type":etype.value,"severity":sev.value,"confidence":conf,"reason":reason,"observation_id":obs.id,"event_id":event.id,"event_code":event.public_code,"created":created,"baseline_rms":bridge.shm_baseline_rms,"baseline_freq":bridge.shm_baseline_freq,"health_score":bridge.health_score,"predicted_days":days,"wo_code":wo_code}
