import { useEffect, useState } from "react";
import { api } from "../api";
import { dualHonesty } from "../honesty.js";

export default function DemoTruth({ events = [], realEngines }) {
  const seed = events.filter((e) => dualHonesty(e).seed).length;
  const fused = events.filter((e) => (e.observation_count || 0) > 1).length;
  const [maps, setMaps] = useState(null);
  useEffect(() => {
    api("/maps/config").then(setMaps).catch(() => setMaps({ enabled: false }));
  }, []);
  return (
    <div className="truth-bar" role="status">
      <div>
        <b>Demonstration data.</b>
        This is not a live city feed.
        {" "}{seed} of {events.length} rows are <span className="tag sim">SEED</span> sample records.
        Fusion ({fused} multi-bus) and work orders are real application code.
        {realEngines != null && (
          <> {realEngines} backend engines are <span className="tag real">REAL</span> (YOLO / ANPR on stills). Phone trigger is <span className="tag rule">RULE_BASED</span>.</>
        )}
        {" "}Map tiles are {maps?.enabled ? <b>Azure Maps</b> : <b>Leaflet + OSM (Azure Maps key not set)</b>}. Leaflet draws the pins either way. Detection is not Azure Maps. UI-only ship is <span className="mono">scripts/ship-ui.ps1</span> (~3 min), not a one-hour rebuild.
      </div>
    </div>
  );
}
