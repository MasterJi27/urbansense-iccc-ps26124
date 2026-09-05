export default function DetectionOverlay({ boxes, compact = false }) {
  if (!boxes?.length) return null;
  return (
    <div className={`rdd-overlay ${compact ? "is-compact" : ""}`} aria-live="polite">
      {boxes.map((row, i) => {
        const box = row.bbox || [];
        if (box.length < 4) return null;
        const [x1, y1, x2, y2] = box;
        const pct = row.confidence != null ? `${Math.round(row.confidence * 100)}%` : "";
        const label = compact
          ? `${row.class_id || row.klass || row.event_type} ${pct}`.trim()
          : `${row.klass || row.event_type} ${pct}${row.hits > 2 ? " lock" : ""}`.trim();
        return (
          <div
            key={row.track_id || `${row.class_id || row.klass}-${i}`}
            className={`rdd-box ${row.event_type === "POTHOLE" ? "is-pothole" : row.event_type === "PEDESTRIAN" ? "is-person" : "is-crack"} ${row.hits > 2 ? "is-locked" : ""}`}
            style={{
              left: `${x1 * 100}%`,
              top: `${y1 * 100}%`,
              width: `${Math.max(0, (x2 - x1) * 100)}%`,
              height: `${Math.max(0, (y2 - y1) * 100)}%`,
            }}
          >
            <span>{label}</span>
          </div>
        );
      })}
    </div>
  );
}
