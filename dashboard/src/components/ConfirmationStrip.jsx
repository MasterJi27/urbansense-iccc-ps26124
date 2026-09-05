import { Link } from "react-router-dom";
import { useUi } from "../i18n.jsx";

function fmt(ts) {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("en-GB", { hour12: false });
  } catch {
    return String(ts);
  }
}

function mergeBuses(...lists) {
  const out = [];
  for (const list of lists) {
    for (const id of list || []) {
      if (id && !out.includes(id)) out.push(id);
    }
  }
  return out;
}

function patrolFoot(state) {
  switch (state) {
    case "FLEET_CONFIRMED":
      return "FLEET_CONFIRMED";
    case "EXPIRED":
      return "EXPIRED";
    case "REPAIR_VERIFIED":
      return "REPAIR_VERIFIED";
    case "FIRST_SIGHTING":
      return "FIRST_SIGHTING";
    default:
      return state || "FIRST_SIGHTING";
  }
}

export default function ConfirmationStrip({ event, ledger, compact = false }) {
  const { t } = useUi();
  if (!event && !ledger) return null;
  const state = ledger?.patrol_state || event?.extra?.patrol_state;
  const confirmed = state === "FLEET_CONFIRMED";
  const expired = state === "EXPIRED";
  const repairOk = state === "REPAIR_VERIFIED";
  const first = ledger?.first_sighting;
  const confirm = ledger?.confirm;
  const buses = mergeBuses(ledger?.unique_buses, event?.extra?.confirming_sources);
  const firstBus = first?.source_id || buses[0] || event?.source_id || "—";
  const secondBus = confirm?.source_id || buses[1] || null;
  const clearPasses = ledger?.clear_passes || event?.extra?.clear_passes || [];
  const repairPasses = ledger?.repair_passes || event?.extra?.repair_passes || [];
  const other = event?.event_type === "OTHER";
  const later = repairOk ? repairPasses : clearPasses;
  const laterIds = later.map((row) => row.source_id || row).filter(Boolean);
  const showAbsence = expired || repairOk || laterIds.length > 0;

  let stripClass = "usp-strip is-first";
  if (confirmed || repairOk) stripClass = "usp-strip is-confirmed";
  if (expired) stripClass = "usp-strip is-expired";

  return (
    <div className={stripClass} role="status">
      <div className="usp-strip-kicker">{t("uspKicker")}</div>
      <p className="usp-strip-line">{other ? t("uspOther") : t("uspLine")}</p>
      {showAbsence && !other ? <p className="muted usp-absence">{t("uspAbsence")}</p> : null}
      {!other && (
      <div className="usp-strip-grid">
        <div className="usp-cell">
          <span className="usp-cell-label">{t("firstSighting")}</span>
          <b>{firstBus}</b>
          <span className="muted">{first?.timestamp ? fmt(first.timestamp) : (confirmed ? "—" : t("unverifiedUntil"))}</span>
          {first?.camera_bay && <span className="tag info">{first.camera_bay}</span>}
        </div>
        <div className={`usp-cell${confirmed || repairOk ? " usp-cell-ok" : ""}`}>
          <span className="usp-cell-label">{confirmed || repairOk ? t("secondBusOk") : t("waitSecond")}</span>
          <b>{secondBus || "—"}</b>
          <span className="muted">{confirm?.timestamp ? fmt(confirm.timestamp) : (confirmed || repairOk ? t("secondBusOk") : "—")}</span>
          {confirm?.camera_bay && <span className="tag real">{confirm.camera_bay}</span>}
          {ledger?.opposite_direction ? <span className="tag real">{t("oppositeDir")}</span> : null}
        </div>
        <div className={`usp-cell${expired || repairOk ? " usp-cell-ok" : ""}`}>
          <span className="usp-cell-label">{expired ? t("expiredState") : repairOk ? t("repairVerified") : t("laterBuses")}</span>
          <b className="table-num">{laterIds.length}</b>
          <span className="muted">{laterIds.length ? laterIds.join(" · ") : t("noResense")}</span>
        </div>
        {!compact && ledger && (
          <div className="usp-cell">
            <span className="usp-cell-label">{t("sameBusIgnored")}</span>
            <b className="table-num">{ledger.same_bus_ignored ?? 0}</b>
            <span className="muted">{t("selfConfirmNo")}</span>
          </div>
        )}
      </div>
      )}
      {event?.public_code && event?.id && (
        <div className="usp-strip-foot">
          <Link className="evlink" to={`/events/${event.id}`}>{event.public_code}</Link>
          <span className="muted"> · {event.event_type} · {other ? t("patrolOther") : patrolFoot(state)}</span>
        </div>
      )}
    </div>
  );
}
