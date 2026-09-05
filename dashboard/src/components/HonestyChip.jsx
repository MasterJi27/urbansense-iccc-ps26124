import { dualHonesty, honestyClass, resolveHonesty } from "../honesty.js";

export default function HonestyChip({ event, status, compact = false }) {
  if (status) {
    return (
      <span className={`tag ${honestyClass(status)}`} title={status} style={compact ? { fontSize: 10 } : undefined}>
        {status}
      </span>
    );
  }
  const dual = dualHonesty(event);
  const fs = compact ? { fontSize: 10 } : undefined;
  if (dual.differ) {
    return (
      <span className="honesty-dual" title={dual.title}>
        <span className={`tag ${honestyClass(dual.payload)}`} style={fs}>{dual.payloadLabel}</span>
        <span className="honesty-sep" aria-hidden="true">·</span>
        <span className={`tag ${honestyClass(dual.engine)}`} style={fs}>engine {dual.engine}</span>
      </span>
    );
  }
  const s = resolveHonesty(event);
  return (
    <span className={`tag ${honestyClass(s)}`} title={s} style={fs}>
      {s}
    </span>
  );
}
