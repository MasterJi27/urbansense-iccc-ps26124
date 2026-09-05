const BAYS = [
  { id: "FRONT", label: "FRONT", note: "road" },
  { id: "LEFT", label: "LEFT", note: "road" },
  { id: "CABIN", label: "CABIN", note: "cabin only" },
  { id: "RIGHT", label: "RIGHT", note: "road" },
  { id: "REAR", label: "REAR", note: "road" },
];

export default function CameraBayDiagram({ present = [], busCode }) {
  const have = new Set((present || []).map((x) => String(x).toUpperCase()));
  return (
    <div className="bay-diagram" aria-label={`${busCode || "Bus"} camera bays`}>
      {busCode && <div className="bay-diagram-title mono">{busCode}</div>}
      <div className="bay-grid">
        {BAYS.map((bay) => {
          const on = have.size === 0 || have.has(bay.id);
          const cabin = bay.id === "CABIN";
          return (
            <div key={bay.id} className={`bay-slot bay-${bay.id.toLowerCase()}${cabin ? " is-cabin" : ""}${on ? " is-on" : ""}`}>
              <b>{bay.label}</b>
              <span>{bay.note}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function bayIdsFromSensors(sensors) {
  return (sensors || [])
    .map((s) => String(s.device_label || s.code || "").replace(/^BUS_CCTV_/, "").replace(/^.*-/, ""))
    .filter(Boolean);
}
