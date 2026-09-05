import { useEffect, useState } from "react";
import { api } from "../api";
import { dualHonesty } from "../honesty.js";

export default function DemoTruth({ events = [], realEngines }) {
  const seed = events.filter((e) => dualHonesty(e).seed).length;
  const live = events.length - seed;
  const fused = events.filter((e) => !dualHonesty(e).seed && (e.observation_count || 0) > 1).length;
  const [maps, setMaps] = useState(null);
  useEffect(() => {
    api("/maps/config").then(setMaps).catch(() => setMaps({ enabled: false }));
  }, []);
  return (
    <div className="truth-bar" role="status">
      <div>
        <b>Live phone detections.</b>
        Lists hide SEED sample rows ({seed} in this load, {live} live).
        Windshield boxes are on-device (road-band + tracker). Azure still is the official event.
        Fusion ({fused} multi-bus) and work orders are real application code.
        {realEngines != null && (
          <> {realEngines} backend engines are <span className="tag real">REAL</span> (RDD on stills).</>
        )}
        {" "}Map tiles are {maps?.enabled ? <b>Azure Maps</b> : <b>OSM fallback</b>}. Detection is not Azure Maps.
      </div>
    </div>
  );
}
